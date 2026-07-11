<?php
/**
 * import-template.php — import an Elementor template JSON onto this site.
 *
 *   wp eval-file import-template.php <file.json>              # into the library
 *   wp eval-file import-template.php <file.json> <post_id>    # and apply to a page
 *
 * Accepts anything the editor's "Import Templates" button accepts, because it
 * hands the file to the exact same code path:
 *
 *   Plugin::$instance->templates_manager->get_source( 'local' )->import_template()
 *
 * That matters for one reason above all: MEDIA. Every media control's
 * `on_import()` hook re-downloads the image referenced by the exported url into
 * THIS site's media library and rewrites the attachment id to the new one. A
 * hand-rolled importer that just writes `_elementor_data` skips those hooks, and
 * the imported block ends up pointing at attachment ids belonging to the site it
 * came from - which on this site are either missing or, much worse, a different
 * image entirely. Silently.
 *
 * With <post_id>, the imported tree is additionally applied to that post so the
 * block becomes a live page rather than a library entry. The library entry is
 * kept (it is what Elementor's own import produces, and it is where the media
 * mapping lives); pass `discard` as the third arg to delete it afterwards.
 */

if ( ! class_exists( '\Elementor\Plugin' ) ) {
	fwrite( STDERR, "Elementor is not active.\n" );
	exit( 1 );
}
if ( empty( $args[0] ) ) {
	fwrite( STDERR, "usage: wp eval-file import-template.php <file.json> [post_id] [discard]\n" );
	exit( 1 );
}

$file = $args[0];
if ( ! is_readable( $file ) ) {
	fwrite( STDERR, "Cannot read {$file}.\n" );
	exit( 1 );
}

$raw = json_decode( file_get_contents( $file ), true );
if ( json_last_error() !== JSON_ERROR_NONE ) {
	fwrite( STDERR, "Invalid JSON: " . json_last_error_msg() . "\n" );
	exit( 1 );
}
foreach ( [ 'content', 'type' ] as $required ) {
	if ( ! isset( $raw[ $required ] ) ) {
		fwrite( STDERR, "Not an Elementor template file: missing `{$required}`.\n" );
		fwrite( STDERR, "Expected keys: content, page_settings, version, title, type.\n" );
		exit( 1 );
	}
}

$source = \Elementor\Plugin::$instance->templates_manager->get_source( 'local' );
if ( ! $source ) {
	fwrite( STDERR, "Elementor's local template source is unavailable.\n" );
	exit( 1 );
}

// import_template() takes the ORIGINAL filename (it switches on the extension to
// decide between a single .json and a .zip of many) and a path to the file.
$result = $source->import_template( basename( $file ), $file );

if ( is_wp_error( $result ) ) {
	fwrite( STDERR, "Import failed: " . $result->get_error_message() . "\n" );
	exit( 1 );
}

// A .json import returns one item; a .zip returns a list.
$items       = isset( $result[0] ) ? $result : [ $result ];
$template_id = (int) ( $items[0]['template_id'] ?? 0 );
if ( ! $template_id ) {
	fwrite( STDERR, "Import returned no template id.\n" );
	exit( 1 );
}

$out = [
	'template_id'    => $template_id,
	'title'          => $items[0]['title'] ?? null,
	'type'           => $items[0]['type'] ?? null,
	'imported_items' => count( $items ),
	'edit_url'       => get_edit_post_link( $template_id, 'raw' ),
];

// Optionally push the imported tree onto a real page.
if ( ! empty( $args[1] ) ) {
	$target = (int) $args[1];
	if ( ! get_post( $target ) ) {
		fwrite( STDERR, "No post {$target} to apply the template to.\n" );
		exit( 1 );
	}

	// Read it back from the imported template, NOT from the file: this is the
	// post-on_import() tree, with attachment ids remapped to this site's media.
	$tree = get_post_meta( $template_id, '_elementor_data', true );
	if ( ! $tree ) {
		fwrite( STDERR, "Imported template {$template_id} has no data.\n" );
		exit( 1 );
	}

	$previous = get_post_meta( $target, '_elementor_data', true );
	if ( $previous ) {
		update_post_meta( $target, '_elementor_data_backup_' . gmdate( 'Ymd_His' ), $previous );
	}

	$target_post = get_post( $target );
	update_post_meta( $target, '_elementor_data', wp_slash( $tree ) );
	update_post_meta( $target, '_elementor_edit_mode', 'builder' );
	update_post_meta( $target, '_elementor_template_type',
		$target_post->post_type === 'page' ? 'wp-page' : 'wp-post' );
	update_post_meta( $target, '_elementor_version', ELEMENTOR_VERSION );

	$css = \Elementor\Core\Files\CSS\Post::create( $target );
	$css->delete();
	$css->update();

	$out['applied_to']    = $target;
	$out['backed_up']     = (bool) $previous;
	$out['permalink']     = get_permalink( $target );

	if ( ( $args[2] ?? '' ) === 'discard' ) {
		wp_delete_post( $template_id, true );
		$out['library_entry'] = 'deleted';
	}
}

echo wp_json_encode( $out, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT ) . "\n";
