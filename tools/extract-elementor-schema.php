<?php
/**
 * extract-elementor-schema.php
 * ---------------------------------------------------------------------------
 * Dump the COMPLETE Elementor authoring surface from a live install: every
 * element type (container / section / column), every widget, every control —
 * with the control's type, default value, allowed options, dependency
 * conditions and the CSS properties it drives — plus the control-type value
 * shapes, the group controls, and the active responsive breakpoints.
 *
 * This is the ground truth behind data/elementor-schema.json and every CSV
 * index derived from it. Nothing in this skill's documentation is written
 * from memory; it is all generated from (or checked against) this dump.
 *
 * USAGE
 *   wp eval-file extract-elementor-schema.php > elementor-schema.json
 *
 * Optional positional arg = source filter. wp eval-file accepts ONLY plain
 * positional args — never `--flag=value`, which WP-CLI intercepts as a global
 * parameter and errors on before this script is reached.
 *
 *   wp eval-file extract-elementor-schema.php core+pro   (default: ship-safe)
 *   wp eval-file extract-elementor-schema.php all        (incl. 3rd-party addons)
 *
 * "core+pro" is the default because third-party addon widgets are specific to
 * whichever site you extracted from and must not be published as if they were
 * part of Elementor.
 *
 * FREE vs PRO
 *   Tier is decided by which plugin directory the class is physically defined
 *   in (elementor/ = free, elementor-pro/ = pro), resolved by reflection.
 *   It is never inferred from a widget's name or apparent sophistication —
 *   that heuristic is wrong (Border and Box Shadow look premium and are free).
 */

if ( ! class_exists( '\Elementor\Plugin' ) ) {
	fwrite( STDERR, "Elementor is not active on this site.\n" );
	exit( 1 );
}

$scope  = isset( $args[0] ) ? $args[0] : 'core+pro';
$plugin = \Elementor\Plugin::$instance;

// ---------------------------------------------------------------------------
// STEP 0 — Defuse Elementor's frontend control-optimisation. Do this BEFORE
// any element's controls are built, or the dump is silently degraded.
//
// Elementor\Core\Frontend\Performance::should_optimize_controls() returns true
// whenever the request is "frontend-ish":
//
//     ! is_admin() && ! is_preview_mode() && ! defined( 'REST_REQUEST' )
//
// A WP-CLI run satisfies all three, so Elementor believes it is rendering the
// front end and switches to its lean control path. Two things then happen:
//
//   1. controls-stack.php — UI controls (heading/divider/raw_html/…) are cut
//      down to just ['type', 'section'], losing their labels.
//   2. managers/controls.php — every *style* control (anything with
//      `selectors`) is diverted into a separate `style_controls` stack, and
//      section markers lose their `label` and their real `tab`, defaulting to
//      'content'.
//
// Measured on Elementor 4.1.4: the container element reports 310 controls
// optimised vs 458 unoptimised — a naive `wp eval-file` extraction silently
// loses 32% of the container's controls and 100% of the tab/label metadata.
// This is the single biggest correctness trap in headless Elementor work, and
// it fails quietly, which is why this script asserts its way out of it below.
// ---------------------------------------------------------------------------
$perf_class = '\Elementor\Core\Frontend\Performance';
if ( class_exists( $perf_class ) ) {
	try {
		$rp = new ReflectionProperty( $perf_class, 'is_frontend' );
		$rp->setAccessible( true );
		$rp->setValue( null, false );
	} catch ( \Throwable $e ) {
		fwrite( STDERR, "FATAL: could not disable Performance::\$is_frontend ({$e->getMessage()}).\n" );
		fwrite( STDERR, "Refusing to emit a silently-degraded schema. Elementor's internals may have changed.\n" );
		exit( 1 );
	}
	if ( $perf_class::should_optimize_controls() ) {
		fwrite( STDERR, "FATAL: control optimisation is still on after disabling it.\n" );
		fwrite( STDERR, "Refusing to emit a silently-degraded schema.\n" );
		exit( 1 );
	}
}

// Labels are translated at control-registration time, so force English before
// anything registers — otherwise the dump inherits the site's locale and ships
// e.g. '背景' where the world expects 'Background'.
if ( function_exists( 'switch_to_locale' ) ) {
	switch_to_locale( 'en_US' );
}

/** Which plugin does this class physically live in? */
function eh_tier_of( $object ) {
	$file = ( new ReflectionClass( $object ) )->getFileName();
	$file = str_replace( '\\', '/', (string) $file );
	if ( strpos( $file, '/elementor-pro/' ) !== false ) {
		return [ 'pro', 'elementor-pro' ];
	}
	if ( strpos( $file, '/plugins/elementor/' ) !== false ) {
		return [ 'free', 'elementor-core' ];
	}
	if ( preg_match( '#/plugins/([^/]+)/#', $file, $m ) ) {
		return [ 'third-party', $m[1] ];
	}
	if ( strpos( $file, '/themes/' ) !== false ) {
		return [ 'third-party', 'theme' ];
	}
	return [ 'unknown', 'unknown' ];
}

/**
 * Pull the CSS property names a control drives, out of its `selectors` map.
 * Elementor selector values look like:
 *   '{{WRAPPER}} .elementor-heading-title' => 'color: {{VALUE}};'
 * We want just: ['color']. This is what makes "which control changes padding?"
 * answerable without reading the whole schema.
 */
function eh_css_props( $ctrl ) {
	if ( empty( $ctrl['selectors'] ) || ! is_array( $ctrl['selectors'] ) ) {
		return [];
	}
	$props = [];
	foreach ( $ctrl['selectors'] as $decl ) {
		if ( ! is_string( $decl ) ) {
			continue;
		}
		// Match "prop:" at the start of a declaration, tolerating -- custom props.
		if ( preg_match_all( '/(?:^|;)\s*([a-zA-Z\-]+(?:--[a-zA-Z0-9\-]+)?)\s*:/', $decl, $m ) ) {
			foreach ( $m[1] as $p ) {
				$props[ $p ] = true;
			}
		}
	}
	return array_values( array_keys( $props ) );
}

/**
 * The OTHER controls whose values this control's CSS interpolates.
 *
 * This is a second, hidden dependency layer that `condition` does not describe,
 * and it fails silently. Elementor's CSS generator
 * (core/files/css/base.php) expands every {{...}} placeholder in a declaration:
 *
 *     if ( '' === $parsed_value ) {
 *         ...
 *         throw new \Exception();
 *     }
 *     } catch ( \Exception $e ) {
 *         return;                 // <- the whole rule is abandoned
 *     }
 *
 * So a declaration like the gradient's
 *
 *     background-image: linear-gradient({{SIZE}}{{UNIT}},
 *         {{background_color.VALUE}} {{background_color_stop.SIZE}}...,
 *         {{background_color_b.VALUE}} ...)
 *
 * emits NOTHING unless background_color and background_color_b are also set —
 * even though every `condition` on it is satisfied. Setting the angle alone, and
 * being surprised that nothing happened, is one of the easiest ways to lose an
 * afternoon in headless Elementor.
 *
 * A placeholder may carry a fallback (`{{a.VALUE || b.VALUE}}`); those do not
 * hard-require the referenced control, so only the fallback-less refs are
 * recorded here.
 */
function eh_needs_value( $ctrl ) {
	if ( empty( $ctrl['selectors'] ) || ! is_array( $ctrl['selectors'] ) ) {
		return [];
	}
	$refs = [];
	foreach ( $ctrl['selectors'] as $decl ) {
		if ( ! is_string( $decl ) ) {
			continue;
		}
		if ( ! preg_match_all( '/\{\{([^}]*)\}\}/', $decl, $m ) ) {
			continue;
		}
		foreach ( $m[1] as $inner ) {
			if ( strpos( $inner, '||' ) !== false ) {
				continue; // has a fallback, so the reference is not required
			}
			$dot = strpos( $inner, '.' );
			if ( $dot === false ) {
				continue; // {{VALUE}}, {{SIZE}}, {{TOP}} - this control's own value
			}
			$name = trim( substr( $inner, 0, $dot ) );
			if ( $name === '' || $name === 'WRAPPER' || $name === 'SELECTOR' ) {
				continue;
			}
			$refs[ $name ] = true;
		}
	}
	return array_keys( $refs );
}

/** Trim option maps to their KEYS — the key is what you write into JSON. */
function eh_option_keys( $ctrl ) {
	if ( empty( $ctrl['options'] ) || ! is_array( $ctrl['options'] ) ) {
		return null;
	}
	$keys = array_keys( $ctrl['options'] );
	// A handful of controls (font pickers) carry hundreds of options; cap them
	// so one control can't dominate the file, and say so explicitly.
	if ( count( $keys ) > 60 ) {
		return [ '__truncated__' => count( $keys ), 'sample' => array_slice( $keys, 0, 20 ) ];
	}
	return $keys;
}

/** Normalise one control into the compact record the skill actually needs. */
function eh_control_record( $name, $ctrl ) {
	$rec = [
		'name' => $name,
		'type' => $ctrl['type'] ?? null,
	];
	if ( ! empty( $ctrl['label'] ) && is_string( $ctrl['label'] ) ) {
		$rec['label'] = $ctrl['label'];
	}
	if ( ! empty( $ctrl['tab'] ) ) {
		$rec['tab'] = $ctrl['tab'];
	}
	if ( ! empty( $ctrl['section'] ) ) {
		$rec['section'] = $ctrl['section'];
	}
	if ( array_key_exists( 'default', $ctrl ) && $ctrl['default'] !== '' && $ctrl['default'] !== null ) {
		$rec['default'] = $ctrl['default'];
	}
	$opts = eh_option_keys( $ctrl );
	if ( $opts !== null ) {
		$rec['options'] = $opts;
	}
	// Dependency: this control only takes effect when another setting matches.
	// Getting this wrong is a silent no-op, so it must be in the data.
	if ( ! empty( $ctrl['condition'] ) ) {
		$rec['condition'] = $ctrl['condition'];
	}
	if ( ! empty( $ctrl['conditions'] ) ) {
		$rec['conditions'] = $ctrl['conditions'];
	}
	$css = eh_css_props( $ctrl );
	if ( $css ) {
		$rec['css'] = $css;
	}
	$needs = eh_needs_value( $ctrl );
	if ( $needs ) {
		$rec['needs_value'] = $needs;
	}
	if ( ! empty( $ctrl['prefix_class'] ) ) {
		$rec['prefix_class'] = $ctrl['prefix_class'];
	}
	if ( isset( $ctrl['return_value'] ) ) {
		$rec['return_value'] = $ctrl['return_value'];
	}
	// Which units this control will accept. Writing `"unit": "pt"` into a
	// control that only allows px/%/em is another silent no-op.
	if ( ! empty( $ctrl['size_units'] ) && is_array( $ctrl['size_units'] ) ) {
		$rec['units'] = array_values( $ctrl['size_units'] );
	}

	// RESPONSIVE. Elementor has TWO mechanisms and they look nothing alike:
	//
	//   1. `is_responsive => true` with an EMPTY `responsive` array. The control
	//      is registered once (e.g. container `padding`) and NO `padding_tablet`
	//      entry exists in the stack at all - the breakpoint variants are
	//      resolved at render time by looking up "{control}_{device}" in the
	//      saved settings. You still write `padding_tablet` into the JSON; there
	//      simply is no control object for it.
	//
	//   2. A non-empty `responsive` args array AND real suffixed siblings in the
	//      stack (e.g. `sticky_offset`, `sticky_offset_tablet`).
	//
	// Testing `! empty( $ctrl['responsive'] )` catches only the second kind and
	// silently misses the first - which is the common one. On the container that
	// is the difference between knowing `padding_tablet` is legal and rejecting
	// it as an unknown control. The authoritative flag is `is_responsive`.
	if ( ! empty( $ctrl['is_responsive'] ) ) {
		$rec['_is_responsive'] = true;
	}
	return $rec;
}

/**
 * Collapse responsive variants. add_responsive_control('width') registers
 * `width`, `width_tablet`, `width_mobile` as three separate stack entries.
 * Emitting all three triples the data for zero new information, so we keep the
 * base control and record `responsive: ["tablet","mobile"]` on it.
 *
 * This is only safe if each suffixed variant really is the base control with a
 * suffix, so we VERIFY that (same control type) and report any variant that
 * doesn't match instead of silently dropping it.
 */
function eh_collapse_responsive( $records, $device_suffixes, &$anomalies, $element_name ) {
	$by_name = [];
	foreach ( $records as $r ) {
		$by_name[ $r['name'] ] = $r;
	}

	$collapsed = [];
	foreach ( $records as $r ) {
		$name = $r['name'];
		$matched_device = null;
		$base = null;
		foreach ( $device_suffixes as $dev ) {
			$suffix = '_' . $dev;
			if ( substr( $name, -strlen( $suffix ) ) === $suffix ) {
				$candidate = substr( $name, 0, -strlen( $suffix ) );
				if ( isset( $by_name[ $candidate ] ) ) {
					$matched_device = $dev;
					$base = $candidate;
					break;
				}
			}
		}

		if ( $matched_device === null ) {
			$collapsed[ $name ] = $r;   // a base control (or a name that merely
			continue;                   // looks suffixed but has no base)
		}

		// It IS a responsive variant. Verify it's structurally the same control.
		if ( ( $by_name[ $base ]['type'] ?? null ) !== ( $r['type'] ?? null ) ) {
			$anomalies[] = [
				'element'   => $element_name,
				'control'   => $name,
				'base'      => $base,
				'reason'    => 'responsive variant type differs from base',
				'base_type' => $by_name[ $base ]['type'] ?? null,
				'var_type'  => $r['type'] ?? null,
			];
			$collapsed[ $name ] = $r;   // keep it — do not hide a mismatch
			continue;
		}
		if ( ! isset( $collapsed[ $base ] ) ) {
			$collapsed[ $base ] = $by_name[ $base ];
		}
		$collapsed[ $base ]['responsive'][] = $matched_device;
	}

	// Merge both mechanisms into one honest answer: the device suffixes you are
	// allowed to append to this control's name. A control flagged `is_responsive`
	// takes every ACTIVE breakpoint even though no suffixed control object exists
	// for it; one with real suffixed siblings takes exactly those.
	foreach ( $collapsed as $k => $v ) {
		$devices = ! empty( $v['responsive'] ) ? $v['responsive'] : [];
		if ( ! empty( $v['_is_responsive'] ) ) {
			$devices = array_merge( $devices, $device_suffixes );
		}
		unset( $collapsed[ $k ]['_is_responsive'] );
		if ( $devices ) {
			$devices = array_values( array_unique( $devices ) );
			sort( $devices );
			$collapsed[ $k ]['responsive'] = $devices;
		} else {
			unset( $collapsed[ $k ]['responsive'] );
		}
	}
	return array_values( $collapsed );
}

/** Walk an element/widget instance into a full record. */
function eh_describe( $name, $obj, $el_type, $device_suffixes, &$anomalies ) {
	try {
		$controls = $obj->get_controls();
	} catch ( \Throwable $e ) {
		return null;
	}
	list( $tier, $source ) = eh_tier_of( $obj );

	$raw = [];
	$sections = [];
	foreach ( $controls as $cname => $ctrl ) {
		if ( ( $ctrl['type'] ?? '' ) === \Elementor\Controls_Manager::SECTION ) {
			$sections[ $cname ] = [
				'name'  => $cname,
				'label' => is_string( $ctrl['label'] ?? null ) ? $ctrl['label'] : null,
				'tab'   => $ctrl['tab'] ?? null,
			];
			continue; // section markers are containers, not settable values
		}
		if ( in_array( $ctrl['type'] ?? '', [ 'tab', 'tabs', 'divider', 'heading', 'raw_html', 'notice', 'alert', 'deprecated_notice' ], true ) ) {
			continue; // pure UI chrome — carries no value you can write
		}
		$raw[] = eh_control_record( $cname, $ctrl );
	}

	$collapsed  = eh_collapse_responsive( $raw, $device_suffixes, $anomalies, $name );
	$responsive = 0;
	foreach ( $collapsed as $c ) {
		if ( ! empty( $c['responsive'] ) ) {
			$responsive++;
		}
	}

	$rec = [
		'name'            => $name,
		'elType'          => $el_type,
		'tier'            => $tier,
		'source'          => $source,
		'controls_total'  => count( $collapsed ),
		'controls_responsive' => $responsive,
		'sections'        => array_values( $sections ),
		'controls'        => $collapsed,
	];
	if ( method_exists( $obj, 'get_title' ) ) {
		$rec['title'] = $obj->get_title();
	}
	if ( method_exists( $obj, 'get_categories' ) ) {
		$rec['categories'] = $obj->get_categories();
	}
	if ( $el_type === 'widget' ) {
		$rec['widgetType'] = $name;
	}
	return $rec;
}

// ---------------------------------------------------------------------------
// 1. Breakpoints — these define the legal responsive suffixes.
// ---------------------------------------------------------------------------
$breakpoints      = [];
$device_suffixes  = [];
if ( isset( $plugin->breakpoints ) && method_exists( $plugin->breakpoints, 'get_active_breakpoints' ) ) {
	foreach ( $plugin->breakpoints->get_active_breakpoints() as $key => $bp ) {
		$breakpoints[ $key ] = [
			'active'    => true,
			'direction' => method_exists( $bp, 'get_direction' ) ? $bp->get_direction() : null,
			'value'     => method_exists( $bp, 'get_value' ) ? $bp->get_value() : null,
			'suffix'    => '_' . $key,
		];
		$device_suffixes[] = $key;
	}
	if ( method_exists( $plugin->breakpoints, 'get_breakpoints' ) ) {
		foreach ( array_keys( $plugin->breakpoints->get_breakpoints() ) as $key ) {
			if ( ! isset( $breakpoints[ $key ] ) ) {
				$breakpoints[ $key ] = [ 'active' => false, 'suffix' => '_' . $key ];
			}
		}
	}
}
// Desktop is the unsuffixed base control — say so rather than leaving a hole.
$breakpoints['desktop'] = [ 'active' => true, 'direction' => 'base', 'value' => null, 'suffix' => '' ];

// ---------------------------------------------------------------------------
// 2. Control types — the JSON value SHAPE for each control type. This is what
//    stops an agent guessing `"padding": "10px"` when Elementor wants a
//    dimensions object.
// ---------------------------------------------------------------------------
$control_types = [];
foreach ( $plugin->controls_manager->get_controls() as $type => $ctrl ) {
	list( $tier, $source ) = eh_tier_of( $ctrl );
	$entry = [
		'type'   => $type,
		'tier'   => $tier,
		'source' => $source,
		'class'  => get_class( $ctrl ),
	];
	if ( method_exists( $ctrl, 'get_default_value' ) ) {
		$entry['value_shape'] = $ctrl->get_default_value();
	}
	$control_types[ $type ] = $entry;
}

// ---------------------------------------------------------------------------
// 3. Group controls — Border, Typography, Background, Box Shadow, Flex, Grid…
//    Each expands into several flat settings keys named {prefix}{field}.
// ---------------------------------------------------------------------------
$group_controls = [];
if ( method_exists( $plugin->controls_manager, 'get_control_groups' ) ) {
	foreach ( $plugin->controls_manager->get_control_groups() as $gname => $group ) {
		list( $tier, $source ) = eh_tier_of( $group );
		$entry = [
			'name'   => $gname,
			'tier'   => $tier,
			'source' => $source,
			'class'  => get_class( $group ),
		];
		try {
			if ( method_exists( $group, 'get_fields' ) ) {
				$fields = $group->get_fields();
				$entry['fields'] = [];
				foreach ( $fields as $fname => $f ) {
					$entry['fields'][] = array_filter( [
						'field'      => $fname,
						'type'       => $f['type'] ?? null,
						'label'      => is_string( $f['label'] ?? null ) ? $f['label'] : null,
						'options'    => eh_option_keys( $f ),
						'responsive' => ! empty( $f['responsive'] ),
					], function ( $v ) { return $v !== null && $v !== false; } );
				}
				$entry['field_count'] = count( $entry['fields'] );
			}
		} catch ( \Throwable $e ) {
			$entry['fields_error'] = $e->getMessage();
		}
		$group_controls[ $gname ] = $entry;
	}
}

// ---------------------------------------------------------------------------
// 4. Elements (container / section / column) + widgets.
// ---------------------------------------------------------------------------
$anomalies = [];
$elements  = [];
foreach ( $plugin->elements_manager->get_element_types() as $name => $el ) {
	$rec = eh_describe( $name, $el, $name, $device_suffixes, $anomalies );
	if ( $rec ) {
		$elements[ $name ] = $rec;
	}
}

// CANARY — prove the metadata really is intact before dumping 20k+ controls.
// With optimisation on, container/background_color reports tab 'content' and
// section markers have no label. With it off, the tab is 'style'. If this
// assertion ever fails, the extraction is degraded and the data must not ship.
$canary_ok = false;
foreach ( $elements['container']['controls'] ?? [] as $c ) {
	if ( $c['name'] === 'background_color' && ( $c['tab'] ?? null ) === 'style' ) {
		$canary_ok = true;
		break;
	}
}
if ( ! $canary_ok ) {
	fwrite( STDERR, "FATAL: canary failed — container/background_color is not reporting tab='style'.\n" );
	fwrite( STDERR, "The control stack is degraded (or Elementor's internals changed). Refusing to emit.\n" );
	exit( 1 );
}

// CANARY 2 — responsive detection. The container's `padding` is the most-used
// responsive control there is; if it comes out non-responsive, the `is_responsive`
// flag has moved and every "_tablet"/"_mobile" key in the schema is now a lie.
$rwd_ok = false;
foreach ( $elements['container']['controls'] ?? [] as $c ) {
	if ( $c['name'] === 'padding' && ! empty( $c['responsive'] ) ) {
		$rwd_ok = true;
		break;
	}
}
if ( ! $rwd_ok ) {
	fwrite( STDERR, "FATAL: canary failed — container/padding is not detected as responsive.\n" );
	fwrite( STDERR, "Elementor's responsive flag has changed. Refusing to emit a schema that would\n" );
	fwrite( STDERR, "reject valid `padding_tablet` keys as unknown controls.\n" );
	exit( 1 );
}

$widgets  = [];
$skipped  = [];
foreach ( $plugin->widgets_manager->get_widget_types() as $name => $w ) {
	// Decide the tier BEFORE calling get_controls(). With optimisation
	// disabled, Elementor wp_die()s on any addon that registers a control
	// outside a section — so a single sloppy third-party plugin would kill the
	// whole extraction. Never build controls we're going to throw away anyway.
	list( $tier, $source ) = eh_tier_of( $w );
	if ( $scope !== 'all' && $tier === 'third-party' ) {
		$skipped[ $source ] = ( $skipped[ $source ] ?? 0 ) + 1;
		continue;
	}
	$rec = eh_describe( $name, $w, 'widget', $device_suffixes, $anomalies );
	if ( $rec ) {
		$widgets[ $name ] = $rec;
	}
}

// ---------------------------------------------------------------------------
// 5. Emit.
// ---------------------------------------------------------------------------
$out = [
	'meta' => [
		'elementor_version'     => defined( 'ELEMENTOR_VERSION' ) ? ELEMENTOR_VERSION : null,
		'elementor_pro_version' => defined( 'ELEMENTOR_PRO_VERSION' ) ? ELEMENTOR_PRO_VERSION : null,
		'php_version'           => PHP_VERSION,
		'scope'                 => $scope,
		'extracted_at'          => gmdate( 'Y-m-d' ),
		'control_optimisation_disabled' => true,
		'third_party_skipped'   => $skipped,
		'counts'                => [
			'elements'      => count( $elements ),
			'widgets'       => count( $widgets ),
			'widgets_free'  => count( array_filter( $widgets, function ( $w ) { return $w['tier'] === 'free'; } ) ),
			'widgets_pro'   => count( array_filter( $widgets, function ( $w ) { return $w['tier'] === 'pro'; } ) ),
			'control_types' => count( $control_types ),
			'group_controls'=> count( $group_controls ),
		],
		'responsive_collapse_anomalies' => $anomalies,
	],
	'breakpoints'    => $breakpoints,
	'control_types'  => $control_types,
	'group_controls' => $group_controls,
	'elements'       => $elements,
	'widgets'        => $widgets,
];

echo json_encode( $out, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
