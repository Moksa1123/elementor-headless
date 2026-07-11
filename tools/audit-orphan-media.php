<?php
/**
 * Find media library attachments that are genuinely unreferenced anywhere
 * on the site — with a guard against the false-positive trap of matching
 * an old attachment ID against an unrelated numeric postmeta value (view
 * counters, analytics object IDs) that happens to share the same integer.
 *
 * Usage: wp eval-file audit-orphan-media.php
 *
 * Read references/plugin-audit-methodology.md ("Step 4") before trusting
 * this script's output — it implements that methodology, but you should
 * understand WHY the false-positive guard exists before acting on a list
 * of "orphans" it produces.
 */

global $wpdb;

function line( $s = '' ) { echo $s . "\n"; }

// Step 1: real reference collection — featured images, inline content,
// any postmeta/option value containing an uploads/ path.
$allAttachments = $wpdb->get_results(
    "SELECT ID, guid, post_title, post_mime_type, post_date FROM {$wpdb->posts} WHERE post_type='attachment'"
);
line( "Total attachments: " . count( $allAttachments ) );

$referencedIds  = [];
$referencedUrls = [];

$thumbs = $wpdb->get_col( "SELECT meta_value FROM {$wpdb->postmeta} WHERE meta_key='_thumbnail_id'" );
foreach ( $thumbs as $t ) { if ( is_numeric( $t ) ) { $referencedIds[ (int) $t ] = true; } }

$metaRows = $wpdb->get_results( "SELECT meta_value FROM {$wpdb->postmeta} WHERE meta_value LIKE '%uploads%'" );
foreach ( $metaRows as $m ) {
    if ( preg_match_all( '#wp-content/uploads/[^"\'\\\\)]+#', $m->meta_value, $mm ) ) {
        foreach ( $mm[0] as $u ) { $referencedUrls[ $u ] = true; }
    }
}

$contentRows = $wpdb->get_results(
    "SELECT post_content FROM {$wpdb->posts} WHERE post_status IN ('publish','private','draft') AND post_content LIKE '%uploads%'"
);
foreach ( $contentRows as $c ) {
    if ( preg_match_all( '#wp-content/uploads/[^"\'\\\\)\s]+#', $c->post_content, $mm ) ) {
        foreach ( $mm[0] as $u ) { $referencedUrls[ $u ] = true; }
    }
}

$optRows = $wpdb->get_results( "SELECT option_value FROM {$wpdb->options} WHERE option_value LIKE '%uploads%'" );
foreach ( $optRows as $o ) {
    if ( preg_match_all( '#wp-content/uploads/[^"\'\\\\)\s]+#', $o->option_value, $mm ) ) {
        foreach ( $mm[0] as $u ) { $referencedUrls[ $u ] = true; }
    }
}

$orphanCandidates = [];
foreach ( $allAttachments as $att ) {
    $filename = basename( $att->guid );
    $found = isset( $referencedIds[ $att->ID ] );
    if ( ! $found ) {
        foreach ( array_keys( $referencedUrls ) as $u ) {
            if ( stripos( $u, $filename ) !== false ) { $found = true; break; }
        }
    }
    if ( ! $found ) { $orphanCandidates[] = $att; }
}
line( "Orphan candidates (pass 1 — URL/thumbnail reference only): " . count( $orphanCandidates ) );

// Step 2 (the false-positive guard): find which ACF fields are actually
// typed to hold image/gallery values, and ONLY cross-check those meta keys
// for bare-integer matches. Do NOT treat every numeric postmeta as a
// potential media reference — most small integers in postmeta are
// unrelated counters that happen to collide with an old low attachment ID.
$acfFields = $wpdb->get_results( "SELECT post_name, post_content FROM {$wpdb->posts} WHERE post_type = 'acf-field'" );
$imageFieldNames = [];
foreach ( $acfFields as $f ) {
    $cfg = @unserialize( $f->post_content );
    if ( is_array( $cfg ) && isset( $cfg['type'] ) && in_array( $cfg['type'], [ 'image', 'gallery' ], true ) ) {
        $imageFieldNames[] = ltrim( $f->post_name, '_' );
    }
}
line( "ACF image/gallery field names found: " . ( $imageFieldNames ? implode( ', ', $imageFieldNames ) : '(none)' ) );

$idSet = array_flip( array_map( fn( $o ) => $o->ID, $orphanCandidates ) );
$foundAsAcfImage = [];
if ( $imageFieldNames ) {
    $placeholders = implode( ',', array_fill( 0, count( $imageFieldNames ), '%s' ) );
    $rows = $wpdb->get_results( $wpdb->prepare(
        "SELECT post_id, meta_key, meta_value FROM {$wpdb->postmeta} WHERE meta_key IN ($placeholders)",
        ...$imageFieldNames
    ) );
    foreach ( $rows as $r ) {
        $vals = [];
        if ( is_numeric( $r->meta_value ) ) {
            $vals[] = (int) $r->meta_value;
        } elseif ( strpos( $r->meta_value, 'a:' ) === 0 ) {
            $un = @unserialize( $r->meta_value );
            if ( is_array( $un ) ) {
                foreach ( $un as $v ) { if ( is_numeric( $v ) ) { $vals[] = (int) $v; } }
            }
        }
        foreach ( $vals as $v ) {
            if ( isset( $idSet[ $v ] ) ) { $foundAsAcfImage[ $v ][] = "{$r->meta_key}(post #{$r->post_id})"; }
        }
    }
}
line( "False positives caught via ACF image-field cross-check: " . count( $foundAsAcfImage ) );
foreach ( $foundAsAcfImage as $id => $refs ) {
    line( "  #$id actually referenced via: " . implode( ', ', $refs ) );
}

$trueOrphans = array_filter( $orphanCandidates, fn( $o ) => ! isset( $foundAsAcfImage[ $o->ID ] ) );

line( '' );
line( str_repeat( '=', 60 ) );
line( "FINAL confirmed orphan count: " . count( $trueOrphans ) );
line( '' );
foreach ( $trueOrphans as $att ) {
    line( sprintf( '  #%d %s [%s] uploaded %s', $att->ID, basename( $att->guid ), $att->post_mime_type, $att->post_date ) );
}
line( '' );
line( 'Reminder: this list is a starting point, not a delete list. Move to a review' );
line( 'folder / trash (not permanent delete) first, spot-check a few by eye, and give' );
line( 'it real time before permanent removal.' );
