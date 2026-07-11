<?php
/**
 * export-template.php — export any Elementor page or template to Elementor's own
 * JSON interchange format, so it can be imported on another site.
 *
 *   wp eval-file export-template.php <post_id> > my-block.json
 *
 * The file this produces is the same format the editor's "Export Template" button
 * produces, and it imports through the editor's "Import Templates" button on any
 * other site. That compatibility is the whole point, so this does not invent a
 * format - it calls Elementor's own document API and assembles the same payload
 * `Local::prepare_template_export()` does.
 *
 * THE FORMAT (verified against includes/template-library/sources/local.php)
 *
 *   {
 *     "content":       [ ...the element tree... ],
 *     "page_settings": { ...document settings... },
 *     "version":       "0.4",          // Elementor\Core\DB::DB_VERSION
 *     "title":         "...",
 *     "type":          "page" | "section" | "container" | "header" | ...
 *   }
 *
 * WHY NOT JUST COPY _elementor_data
 *
 * Because of images. `get_export_data()` runs every control through its
 * `on_export()` hook, and `Control_Media::on_export()` strips the attachment `id`
 * and keeps the `url`. On import, `on_import()` re-downloads that url into the
 * target site's media library and rewrites the id to the NEW attachment.
 *
 * Copy `_elementor_data` verbatim between sites and the ids survive - pointing at
 * attachment ids that mean something completely different on the other site, or
 * nothing at all. The images silently break, or worse, silently become the wrong
 * images. This is the one job you must not do by hand.
 */

if ( ! class_exists( '\Elementor\Plugin' ) ) {
	fwrite( STDERR, "Elementor is not active.\n" );
	exit( 1 );
}
if ( empty( $args[0] ) ) {
	fwrite( STDERR, "usage: wp eval-file export-template.php <post_id> [type]\n" );
	fwrite( STDERR, "  type overrides the exported template type (page/section/container/header/...)\n" );
	exit( 1 );
}

$post_id = (int) $args[0];
$post    = get_post( $post_id );
if ( ! $post ) {
	fwrite( STDERR, "No post {$post_id}.\n" );
	exit( 1 );
}

$document = \Elementor\Plugin::$instance->documents->get( $post_id );
if ( ! $document ) {
	fwrite( STDERR, "Post {$post_id} is not an Elementor document.\n" );
	exit( 1 );
}

// on_export runs here: media ids are dropped in favour of urls, dynamic tags are
// normalised, etc. Do not shortcut this by reading _elementor_data directly.
$data = $document->get_export_data();

if ( empty( $data['content'] ) ) {
	fwrite( STDERR, "Post {$post_id} has no Elementor content.\n" );
	exit( 1 );
}

$content = apply_filters(
	'elementor/template_library/sources/local/export/elements',
	$data['content']
);

// Elementor's own exporter only handles the elementor_library CPT. A normal page
// exports fine as a `page` template; anything already in the library keeps its
// declared type so it lands back in the right Theme Builder slot.
$type = isset( $args[1] ) ? (string) $args[1] : null;
if ( ! $type ) {
	$type = get_post_meta( $post_id, '_elementor_template_type', true );
	if ( ! $type || $type === 'wp-page' || $type === 'wp-post' ) {
		$type = 'page';
	}
}

// The format version Elementor stamps on its own exports. It lives on
// \Elementor\DB (includes/db.php, namespace Elementor) - NOT \Elementor\Core\DB,
// which does not exist. Read it from the class rather than hardcoding '0.4', so
// this file keeps matching Elementor's exporter when the format moves.
echo wp_json_encode( [
	'content'       => $content,
	'page_settings' => $data['settings'] ?? [],
	'version'       => \Elementor\DB::DB_VERSION,
	'title'         => $post->post_title,
	'type'          => $type,
], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
