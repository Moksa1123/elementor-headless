<?php
/**
 * apply-page.php — write an Elementor page tree into a post, headlessly.
 *
 *   wp eval-file apply-page.php <post_id> <page.json>
 *
 * wp eval-file takes plain positional args ONLY. Never `--flag=value`: WP-CLI
 * grabs any `--foo=bar` token as one of its own global parameters and errors out
 * before this script is reached.
 *
 * WHAT ELEMENTOR NEEDS, BEYOND THE TREE
 * Writing `_elementor_data` alone is not enough, and the failure is silent - the
 * post saves, the page loads, and it renders as if Elementor were not involved:
 *
 *   _elementor_data           the tree, JSON-encoded (this is the page)
 *   _elementor_edit_mode      must be 'builder', or the theme renders post_content
 *   _elementor_template_type  'wp-page' / 'wp-post', or the editor mis-handles it
 *   _elementor_version        stamped so Elementor knows which upgrades to run
 *
 * Then TWO caches have to be dropped, and each one independently makes a correct
 * tree render wrong:
 *
 *   the compiled CSS   uploads/elementor/css/post-<id>.css - the page keeps the
 *                      OLD styling until it is rebuilt (`wp elementor flush-css`)
 *   the rendered HTML  the `_elementor_element_cache` post meta - the page keeps
 *                      the OLD markup, served straight back by Elementor
 *
 * Elementor's own Document::save() clears both. Writing the meta directly clears
 * neither, and nothing warns you.
 *
 * This script does the meta, the CSS rebuild and the HTML cache. Any page cache
 * (Breeze/Varnish/Cloudflare) still has to be purged on top.
 */

if ( ! class_exists( '\Elementor\Plugin' ) ) {
	fwrite( STDERR, "Elementor is not active.\n" );
	exit( 1 );
}
if ( count( $args ) < 2 ) {
	fwrite( STDERR, "usage: wp eval-file apply-page.php <post_id> <page.json>\n" );
	exit( 1 );
}

$post_id = (int) $args[0];
$file    = $args[1];

$post = get_post( $post_id );
if ( ! $post ) {
	fwrite( STDERR, "No post {$post_id}.\n" );
	exit( 1 );
}
if ( ! is_readable( $file ) ) {
	fwrite( STDERR, "Cannot read {$file}.\n" );
	exit( 1 );
}

$json = file_get_contents( $file );
$tree = json_decode( $json, true );
if ( json_last_error() !== JSON_ERROR_NONE ) {
	fwrite( STDERR, "Invalid JSON: " . json_last_error_msg() . "\n" );
	exit( 1 );
}
if ( ! is_array( $tree ) || ! isset( $tree[0] ) ) {
	fwrite( STDERR, "The tree must be a JSON list of top-level elements.\n" );
	exit( 1 );
}

// Structural sanity. Deep validation belongs in tools/validate-page.py, which
// can see the schema; this is the last line of defence against writing a tree
// that would brick the editor.
$ids = [];
$check = function ( $nodes, $path ) use ( &$check, &$ids ) {
	foreach ( $nodes as $i => $el ) {
		$at = "{$path}[{$i}]";
		if ( empty( $el['id'] ) ) {
			fwrite( STDERR, "FATAL: {$at} has no id.\n" );
			exit( 1 );
		}
		if ( isset( $ids[ $el['id'] ] ) ) {
			fwrite( STDERR, "FATAL: {$at} duplicates id '{$el['id']}' (first seen at {$ids[$el['id']]}).\n" );
			exit( 1 );
		}
		$ids[ $el['id'] ] = $at;
		if ( ! isset( $el['elements'] ) || ! is_array( $el['elements'] ) ) {
			fwrite( STDERR, "FATAL: {$at} has no `elements` array.\n" );
			exit( 1 );
		}
		if ( ( $el['elType'] ?? '' ) === 'widget' && empty( $el['widgetType'] ) ) {
			fwrite( STDERR, "FATAL: {$at} is a widget with no widgetType.\n" );
			exit( 1 );
		}
		$check( $el['elements'], "{$at}.elements" );
	}
};
$check( $tree, '' );

// Keep a copy of whatever was there, so this is reversible.
$previous = get_post_meta( $post_id, '_elementor_data', true );
if ( $previous ) {
	update_post_meta( $post_id, '_elementor_data_backup_' . gmdate( 'Ymd_His' ), $previous );
}

// wp_slash: WordPress unslashes on the way in, so unescaped content would lose
// its backslashes. Elementor's own save path slashes for the same reason.
update_post_meta( $post_id, '_elementor_data', wp_slash( wp_json_encode( $tree ) ) );
update_post_meta( $post_id, '_elementor_edit_mode', 'builder' );
update_post_meta( $post_id, '_elementor_template_type', $post->post_type === 'page' ? 'wp-page' : 'wp-post' );
update_post_meta( $post_id, '_elementor_version', ELEMENTOR_VERSION );

// Rebuild this post's compiled CSS, or the page renders with the previous styling.
$css = \Elementor\Core\Files\CSS\Post::create( $post_id );
$css->delete();
$css->update();

// AND drop the rendered-HTML cache, or the page renders with the previous MARKUP.
//
// Elementor stores the HTML it rendered for each element in a `_elementor_element_cache`
// post meta and serves that straight back from get_builder_content_for_display().
// Its own Document::save() drops the meta; writing `_elementor_data` directly does
// not, so the new tree is stored, the CSS is rebuilt around it, and the front end
// keeps serving the OLD markup until the cache TTL expires.
//
// This is the worst class of failure this project has: it looks like it worked.
// The post updates, the css file changes, `wp post meta get _elementor_data` reads
// back exactly what you wrote - and the page is unchanged. It went unnoticed here
// through an entire CSS-level verification sweep, because CSS is a separate file
// that we always rebuilt. It only surfaced on the first sweep that read the HTML.
//
// Referenced through the class constant on purpose: if Elementor renames the meta
// key, this line fails loudly instead of silently clearing nothing.
$cache_key = \Elementor\Core\Base\Document::CACHE_META_KEY;
$had_cache = (bool) get_post_meta( $post_id, $cache_key, true );
delete_post_meta( $post_id, $cache_key );

$count = 0;
$walk  = function ( $nodes ) use ( &$walk, &$count ) {
	foreach ( $nodes as $el ) {
		$count++;
		$walk( $el['elements'] ?? [] );
	}
};
$walk( $tree );

echo json_encode( [
	'post_id'        => $post_id,
	'elements'       => $count,
	'unique_ids'     => count( $ids ),
	'backed_up'      => (bool) $previous,
	'html_cache_cleared' => $had_cache,
	'css_file'       => $css->get_url(),
	'permalink'      => get_permalink( $post_id ),
	'post_status'    => get_post_status( $post_id ),
], JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT ) . "\n";
