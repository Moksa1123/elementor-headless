<?php
/**
 * Cross-reference a plugin's REAL signature (block name, shortcode tag, or
 * option key — NOT the plugin slug) across post content, Elementor data,
 * and site options.
 *
 * You must find the real signature yourself first — see
 * references/plugin-audit-methodology.md for how. This script does not
 * guess it for you; guessing is exactly the mistake it exists to prevent.
 *
 * Usage (plain positional args — wp-cli's eval-file does NOT support a `--`
 * separator or `--flag=value` style options; any `--foo=bar` token is
 * intercepted by wp-cli itself as an attempted GLOBAL parameter and errors
 * out before your script ever runs):
 *
 *   wp eval-file audit-plugin-usage.php "kevinbatdorf/code-block-pro"
 *   wp eval-file audit-plugin-usage.php "connectors_ai_openai_api_key" option
 *
 * $args[0] = the real signature to search for.
 * $args[1] = optional type hint (currently unused for filtering, reserved).
 */

global $wpdb;

function line( $s = '' ) { echo $s . "\n"; }

$signature = isset( $args[0] ) ? $args[0] : null;
$type      = isset( $args[1] ) ? $args[1] : 'auto';

if ( ! $signature ) {
    line( 'Usage: wp eval-file audit-plugin-usage.php "<real-signature>" [type-hint]' );
    line( 'Find the real signature first (block.json name, add_shortcode() tag, or option key) — see references/plugin-audit-methodology.md' );
    exit( 1 );
}

line( "Auditing usage of: {$signature}  (type={$type})" );
line( str_repeat( '=', 60 ) );

// 1. post_content across all statuses worth checking
$rows = $wpdb->get_results( $wpdb->prepare(
    "SELECT ID, post_title, post_type, post_status FROM {$wpdb->posts}
     WHERE post_content LIKE %s AND post_status IN ('publish','draft','future','private')",
    '%' . $wpdb->esc_like( $signature ) . '%'
) );
line( '' );
line( 'post_content matches: ' . count( $rows ) );
foreach ( $rows as $r ) {
    line( "  #{$r->ID} {$r->post_title} ({$r->post_type}/{$r->post_status})" );
}

// 2. _elementor_data (Elementor widgets store their type/settings here, not in post_content)
$rows = $wpdb->get_results( $wpdb->prepare(
    "SELECT p.ID, p.post_title, p.post_type
     FROM {$wpdb->postmeta} pm
     JOIN {$wpdb->posts} p ON p.ID = pm.post_id
     WHERE pm.meta_key = '_elementor_data' AND pm.meta_value LIKE %s",
    '%' . $wpdb->esc_like( $signature ) . '%'
) );
line( '' );
line( '_elementor_data matches: ' . count( $rows ) );
foreach ( $rows as $r ) {
    line( "  #{$r->ID} {$r->post_title} ({$r->post_type})" );
}

// If Elementor data matched, walk the widget tree and report which widgetType/path it's at,
// and whether that template/post has live Theme Builder conditions.
if ( $rows ) {
    line( '' );
    line( 'Elementor widget tree detail (widgetType + Theme Builder liveness):' );
    foreach ( $rows as $r ) {
        $raw = get_post_meta( $r->ID, '_elementor_data', true );
        $data = json_decode( $raw, true );
        if ( ! is_array( $data ) ) { continue; }
        $conditions = get_post_meta( $r->ID, '_elementor_conditions', true );
        $live = ! empty( $conditions ) ? 'LIVE (' . implode( ' | ', (array) $conditions ) . ')' : 'no _elementor_conditions — check for direct embeds elsewhere';
        line( "  #{$r->ID}: {$live}" );
        $matches = [];
        $walk = function ( $els ) use ( &$walk, &$matches, $signature ) {
            foreach ( $els as $e ) {
                $blob = json_encode( $e );
                if ( strpos( $blob, $signature ) !== false && ! empty( $e['widgetType'] ) ) {
                    $matches[] = $e['widgetType'];
                }
                if ( ! empty( $e['elements'] ) ) { $walk( $e['elements'] ); }
            }
        };
        $walk( $data );
        foreach ( array_count_values( $matches ) as $wt => $n ) {
            line( "    widgetType={$wt} x{$n}" );
        }
    }
}

// 3. options table (settings/config-based usage)
$rows = $wpdb->get_results( $wpdb->prepare(
    "SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE %s OR option_value LIKE %s LIMIT 50",
    '%' . $wpdb->esc_like( $signature ) . '%',
    '%' . $wpdb->esc_like( $signature ) . '%'
) );
line( '' );
line( 'wp_options matches: ' . count( $rows ) );
foreach ( $rows as $r ) {
    line( "  {$r->option_name}" );
}

line( '' );
line( str_repeat( '=', 60 ) );
$total = count( $wpdb->get_results( $wpdb->prepare(
    "SELECT ID FROM {$wpdb->posts} WHERE post_content LIKE %s",
    '%' . $wpdb->esc_like( $signature ) . '%'
) ) );
if ( $total === 0 && empty( $rows ) ) {
    line( 'No matches anywhere for this signature.' );
    line( 'Before concluding "unused": are you SURE this is the real block name / shortcode' );
    line( 'tag / option key, confirmed from the plugin\'s own source — not guessed from its slug?' );
} else {
    line( 'Found usage. Do not deactivate/delete without checking the detail above.' );
}
