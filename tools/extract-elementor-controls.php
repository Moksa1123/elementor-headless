<?php
/**
 * Extract every registered Elementor widget's control schema from a LIVE
 * install — the ground-truth source for references/elementor-widgets-and-containers.md
 * and data/elementor-core-pro-controls.json. Re-run this against your own
 * site to get current data for your installed Elementor version and any
 * third-party addon widgets it has.
 *
 * Usage: wp eval-file extract-elementor-controls.php > controls-dump.json
 * (or pass a source filter as $args[0]: "elementor-core", "elementor-pro",
 *  or a plugin folder name, to only dump matching widgets)
 *
 * KNOWN GAP (confirmed by reading Elementor Pro source, not guessed): Border,
 * Box-Shadow, and Custom CSS controls are injected by Elementor Pro via
 * action hooks tied to specific section IDs (see
 * elementor-pro/modules/custom-css/module.php for the exact mechanism),
 * not registered as part of a widget's own _register_controls(). A plain
 * get_controls() call like this one will NOT capture those fields — their
 * section markers (_section_border, section_custom_css) will show up with
 * little or nothing inside them. If you need those specific fields, read
 * the relevant Pro module's source directly for your installed version.
 */

if ( ! class_exists( '\Elementor\Plugin' ) ) {
    fwrite( STDERR, "Elementor is not active on this site.\n" );
    exit( 1 );
}

$source_filter = isset( $args[0] ) ? $args[0] : null;

$widgets_manager = \Elementor\Plugin::$instance->widgets_manager;
$widget_types = $widgets_manager->get_widget_types();

$result = [];
foreach ( $widget_types as $name => $widget ) {
    try {
        $controls = $widget->get_controls();
    } catch ( \Throwable $e ) {
        continue;
    }

    $ref = new ReflectionClass( $widget );
    $file = $ref->getFileName();
    $source = 'unknown';
    if ( strpos( $file, '/plugins/elementor-pro/' ) !== false ) { $source = 'elementor-pro'; }
    elseif ( strpos( $file, '/plugins/elementor/' ) !== false ) { $source = 'elementor-core'; }
    elseif ( strpos( $file, '/plugins/' ) !== false ) {
        preg_match( '#/plugins/([^/]+)/#', $file, $m );
        $source = $m[1] ?? 'unknown-plugin';
    } elseif ( strpos( $file, '/themes/' ) !== false ) { $source = 'theme'; }

    if ( $source_filter && $source !== $source_filter ) { continue; }

    $simplified = [];
    foreach ( $controls as $ctrl_name => $ctrl ) {
        $simplified[] = [
            'name'    => $ctrl_name,
            'type'    => $ctrl['type'] ?? null,
            'label'   => $ctrl['label'] ?? null,
            'section' => $ctrl['section'] ?? null,
        ];
    }

    $result[ $name ] = [
        'title'         => method_exists( $widget, 'get_title' ) ? $widget->get_title() : null,
        'source'        => $source,
        'categories'    => method_exists( $widget, 'get_categories' ) ? $widget->get_categories() : [],
        'control_count' => count( $simplified ),
        'controls'      => $simplified,
    ];
}

echo json_encode( $result, JSON_UNESCAPED_SLASHES );
