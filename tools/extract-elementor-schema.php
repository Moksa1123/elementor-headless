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
 * Which Elementor MODULE registered this widget.
 *
 * It is in the class's own file path — `modules/woocommerce/widgets/products.php`
 * — so there is nothing to guess. This matters because a module is not
 * unconditional: several of them refuse to load unless something else is true, and
 * when they do not load, their widgets DO NOT EXIST. See eh_module_gates().
 */
function eh_module_of( $object ) {
	$file = str_replace( '\\', '/', (string) ( new ReflectionClass( $object ) )->getFileName() );
	if ( preg_match( '#/modules/([^/]+)/#', $file, $m ) ) {
		return $m[1];
	}
	return null;
}

/**
 * The gate on every Elementor Pro module, and whether it is currently open.
 *
 * THE WIDGET SURFACE IS NOT A PROPERTY OF ELEMENTOR. It is a property of the
 * INSTALL. On Elementor Pro 4.1.2:
 *
 *   woocommerce      class_exists( 'woocommerce' )        36 widgets, gone without WooCommerce
 *   mega-menu        experiment 'nested-elements'
 *   nested-carousel  experiment 'nested-elements'
 *   off-canvas       experiment 'nested-elements'
 *
 * A schema extracted on a site without WooCommerce says "163 widgets" and contains
 * no `woocommerce-product-price`. Ask it and it will tell you, with total
 * confidence, that no such widget exists. That is not a missing feature; it is the
 * schema asserting something false about Elementor.
 *
 * So the extraction records what was true of the machine it ran on, and every
 * widget records the module it came from. Then a consumer can tell the difference
 * between "Elementor has no such widget" and "this schema was taken somewhere that
 * could not see it".
 */
function eh_module_gates() {
	$out   = [];
	$roots = [];
	if ( defined( 'ELEMENTOR_PATH' ) ) {
		$roots['Elementor\\Modules\\'] = ELEMENTOR_PATH . 'modules/';
	}
	if ( defined( 'ELEMENTOR_PRO_PATH' ) ) {
		$roots['ElementorPro\\Modules\\'] = ELEMENTOR_PRO_PATH . 'modules/';
	}
	foreach ( $roots as $ns => $root ) {
		foreach ( glob( $root . '*', GLOB_ONLYDIR ) as $dir ) {
			$slug = basename( $dir );
			$src  = $dir . '/module.php';
			if ( ! is_readable( $src ) ) {
				continue;
			}
			$body = file_get_contents( $src );

			// A module that DECLARES ITS OWN EXPERIMENT is gated on it, full stop.
			// This is the strongest signal there is and it does not depend on what
			// the gate method happens to be called - Elementor Pro's atomic-form
			// gates in `is_experiment_active()`, not `is_active()`, and matching on
			// the method name alone silently misses its 10 widgets.
			$own_exp = null;
			if ( preg_match( "#const\s+EXPERIMENT_NAME\s*=\s*'([^']+)'#", $body, $ce ) ) {
				$own_exp = $ce[1];
			}

			// The gate as written, straight out of the source. Not paraphrased: if
			// Elementor changes what a module depends on, this changes with it.
			$gate = null;
			if ( preg_match( '#function\s+is_(?:experiment_)?active\s*\([^)]*\)\s*(?::\s*\w+\s*)?\{\s*return\s+(.+?);#s',
				$body, $m ) ) {
				$gate = trim( preg_replace( '/\s+/', ' ', $m[1] ) );
			}
			if ( $gate === null && $own_exp === null ) {
				continue;
			}
			if ( $gate === 'true' && $own_exp === null ) {
				continue;   // unconditional — nothing to disclose
			}
			$gate = $gate ?? "experiment {$own_exp}";
			// Most gates read an EXPERIMENT. The experiment's name is usually a
			// class constant (`self::EXPERIMENT_NAME`), so resolve it - "requires
			// the experiment self::EXPERIMENT_NAME" helps nobody.
			// PRIORITY MATTERS, and getting it backwards shipped 21 wrong
			// requirements. The authoritative source is what the GATE actually
			// checks: Pro's floating-buttons module declares
			// EXPERIMENT_NAME='floating-buttons' but its is_active() gates on
			// class_exists + is_feature_active('container'). Preferring the
			// module's own constant claimed widgets need an experiment that is
			// off on a site where all of them are registered and rendering.
			// The own constant is a FALLBACK for modules whose gate could not
			// be parsed (atomic-form's is_experiment_active), nothing more.
			$experiment = null;
			if ( preg_match( "#is_feature_active\(\s*'([^']+)'#", $gate, $e ) ) {
				$experiment = $e[1];
			} elseif ( preg_match( '#is_feature_active\(\s*(?:self::)?([A-Z_]+)#', $gate, $e )
				&& preg_match( "#const\s+{$e[1]}\s*=\s*'([^']+)'#", $body, $c ) ) {
				$experiment = $c[1];
			} elseif ( preg_match( '#is_feature_active\(\s*\\\\?([\w\\\\]+)::([A-Z_]+)#', $gate, $e ) ) {
				// The constant lives on ANOTHER module's class, and it is reached
				// two different ways:
				//
				//   \Elementor\Modules\NestedElements\Module::EXPERIMENT_NAME   (fqn)
				//   NestedElementsModule::EXPERIMENT_NAME                        (aliased import)
				//
				// so resolve the alias through the file's own `use` statements
				// first. Then note the class path ends in `Module` - the module
				// name is the segment BEFORE that; taking the last one just gives
				// you the string "Module".
				$ref = $e[1];
				if ( strpos( $ref, '\\' ) === false
					&& preg_match( '#use\s+([\w\\\\]+)\s+as\s+' . preg_quote( $ref, '#' ) . '\s*;#', $body, $u ) ) {
					$ref = $u[1];
				}
				$parts = explode( '\\', trim( $ref, '\\' ) );
				array_pop( $parts );                       // drop the trailing "Module"
				$dir_name = strtolower( preg_replace( '/(?<!^)[A-Z]/', '-$0', (string) array_pop( $parts ) ) );
				foreach ( $roots as $r ) {
					$other = $r . $dir_name . '/module.php';
					if ( is_readable( $other )
						&& preg_match( "#const\s+{$e[2]}\s*=\s*'([^']+)'#", file_get_contents( $other ), $c ) ) {
						$experiment = $c[1];
						break;
					}
				}
			}
			if ( $experiment === null && strpos( $gate, 'is_feature_active' ) === false ) {
				$experiment = null;   // the gate does not check experiments at all
			} elseif ( $experiment === null ) {
				$experiment = $own_exp;   // gate checks one, unparseable: fall back
			}
			// An EXTERNAL plugin requirement, e.g. `class_exists( 'woocommerce' )`.
			// Several modules also class_exists() their way to an Elementor class
			// (`class_exists( 'Elementor\Modules\FloatingButtons\Module' )`) — that
			// is an internal availability check, not a dependency on anything the
			// user has to install, and reporting it as "requires
			// Elementor\Modules\FloatingButtons\Module" would be noise dressed up
			// as a fact.
			$plugin = null;
			if ( preg_match( "#class_exists\(\s*'([^']+)'#", $gate, $p )
				&& stripos( $p[1], 'Elementor' ) !== 0 ) {
				$plugin = $p[1];
			}

			$cls    = $ns . str_replace( ' ', '', ucwords( str_replace( '-', ' ', $slug ) ) ) . '\\Module';
			$active = null;
			if ( class_exists( $cls ) && method_exists( $cls, 'is_active' ) ) {
				try {
					$active = (bool) $cls::is_active();
				} catch ( \Throwable $e ) {
					$active = null;
				}
			}
			$rec = [ 'gate' => $gate, 'active' => $active ];
			if ( $experiment ) {
				$rec['experiment'] = $experiment;
			}
			if ( $plugin ) {
				$rec['plugin_class'] = $plugin;
			}
			$out[ $slug ] = $rec;
		}
	}
	return $out;
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
 * WHERE the CSS lands. Not the same question as WHICH property it sets.
 *
 * The keys of the `selectors` map are selector templates:
 *
 *     '{{WRAPPER}} .elementor-heading-title' => 'color: {{VALUE}};'
 *
 * so `title_color` does NOT style the element wrapper — it styles a node INSIDE it.
 * Knowing only the property name is enough to grep the compiled stylesheet and see
 * the rule is present, which is what every text-level check in this repo did. It is
 * NOT enough to ask a browser what the element actually computes: query the wrapper
 * for `color` and you get the inherited value, and a page that renders perfectly
 * looks broken.
 *
 * `{{WRAPPER}}` is the element's own `.elementor-element-<id>`; what remains is the
 * path from it to the node the rule really targets.
 */
function eh_css_selectors( $ctrl ) {
	if ( empty( $ctrl['selectors'] ) || ! is_array( $ctrl['selectors'] ) ) {
		return [];
	}
	$out = [];
	foreach ( $ctrl['selectors'] as $sel => $decl ) {
		if ( ! is_string( $sel ) ) {
			continue;
		}
		$sel = trim( preg_replace( '/\s+/', ' ', $sel ) );
		// VERBATIM, with `{{WRAPPER}}` left in place. It is not always a prefix
		// followed by a space, and treating it as one is lossy:
		//
		//     {{WRAPPER}} .elementor-heading-title                 descendant
		//     {{WRAPPER}}.elementor-view-stacked .elementor-icon   compound - NO space
		//     {{WRAPPER}}:not(.elementor-motion-effects-element…)  pseudo, attached
		//     {{WRAPPER}}:hover .elementor-button                  a hover state
		//     (desktop+){{WRAPPER}} > .elementor-widget-container  device-scoped
		//     a, b                                                 a comma-separated LIST
		//
		// Stripping "{{WRAPPER}} " turned the compound ones into descendant ones,
		// which match nothing. The consumer substitutes `.elementor-element-<id>`
		// for `{{WRAPPER}}` and gets a selector that is exactly what Elementor
		// compiled. Nothing is thrown away for the sake of a few bytes in a file
		// that is not loaded into context anyway.
		if ( $sel === '' ) {
			continue;
		}
		// EACH SELECTOR WITH THE PROPERTIES IT SETS, kept paired.
		//
		// Flattening a control's properties into one list and its selectors into
		// another THROWS THE PAIRING AWAY, and the pairing is the whole answer for
		// half these controls. icon-box `primary_color`:
		//
		//   {{WRAPPER}}.elementor-view-stacked .elementor-icon -> background-color
		//   {{WRAPPER}}.elementor-view-framed  .elementor-icon -> color, border-color
		//
		// Two selectors, DIFFERENT properties, and which pair applies depends on
		// another control (`view`). Flattened, the schema says primary_color sets
		// `color` on `.elementor-view-stacked .elementor-icon` - and it does not;
		// `secondary_color` does. A text check never notices, because `color:` IS in
		// that element's rules. A browser notices immediately: it computes white.
		$props = [];
		if ( is_string( $decl ) && preg_match_all(
			'/(?:^|;)\s*([a-zA-Z\-]+(?:--[a-zA-Z0-9\-]+)?)\s*:/', $decl, $m ) ) {
			$props = array_values( array_unique( $m[1] ) );
		}
		$out[] = [ 'sel' => $sel, 'props' => $props ];
	}
	return $out;
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
		$sel = eh_css_selectors( $ctrl );
		if ( $sel ) {
			$rec['css_selectors'] = $sel;
		}
	}
	$needs = eh_needs_value( $ctrl );
	if ( $needs ) {
		$rec['needs_value'] = $needs;
	}
	// PREFIX CLASS. The other way a control can act: instead of (or as well as)
	// emitting CSS, it appends `prefix_class . value` to the element's wrapper
	// class list. Gated by conditions just like CSS is (get_settings_for_display()
	// nulls out any control whose condition is unmet), but it never appears in the
	// stylesheet, so the CSS sweep is blind to it.
	if ( ! empty( $ctrl['prefix_class'] ) ) {
		$rec['prefix_class'] = $ctrl['prefix_class'];
	}
	// ...and the value that gets appended is NOT always the value you wrote.
	// `classes_dictionary` remaps it first (element-base.php:800). It exists so
	// that pages saved before Elementor moved to logical properties keep working:
	// icon-box `position` accepts the legacy `top` and renders `block-start`.
	// Miss this and you conclude `top` is an invalid option — it is not.
	if ( ! empty( $ctrl['classes_dictionary'] ) && is_array( $ctrl['classes_dictionary'] ) ) {
		$rec['classes_dictionary'] = $ctrl['classes_dictionary'];
	}
	if ( isset( $ctrl['return_value'] ) ) {
		$rec['return_value'] = $ctrl['return_value'];
	}

	// REPEATER FIELDS. A repeater's value is a LIST OF OBJECTS, and the objects'
	// keys are defined per control - a form's `form_fields` item is nothing like an
	// icon-list's `icon_list` item. Without capturing `fields`, the schema can say
	// "slides is a repeater" and nothing else, and an agent building a slider, a
	// form, tabs or a price list is back to guessing key names - the exact failure
	// this project exists to prevent. (The editor also stamps a unique `_id` on
	// every item; headlessly you write it yourself, 7 lowercase hex like element
	// ids.)
	if ( ! empty( $ctrl['fields'] ) && is_array( $ctrl['fields'] ) ) {
		$fields = [];
		foreach ( $ctrl['fields'] as $fname => $f ) {
			if ( ! is_array( $f ) ) {
				continue;
			}
			$fkey = is_string( $fname ) ? $fname : ( $f['name'] ?? null );
			if ( ! $fkey ) {
				continue;
			}
			$ftype = $f['type'] ?? '';
			if ( in_array( $ftype, [ 'section', 'tab', 'tabs', 'divider', 'heading', 'raw_html', 'notice', 'alert' ], true ) ) {
				continue;
			}
			$fr = [ 'name' => $fkey, 'type' => $ftype ];
			$fopts = eh_option_keys( $f );
			if ( $fopts ) {
				$fr['options'] = $fopts;
			}
			if ( isset( $f['default'] ) && $f['default'] !== '' && $f['default'] !== [] ) {
				$fr['default'] = $f['default'];
			}
			if ( ! empty( $f['condition'] ) ) {
				$fr['condition'] = $f['condition'];
			}
			$fields[] = $fr;
		}
		if ( $fields ) {
			$rec['fields'] = $fields;
		}
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

		// A responsive control that emits a CLASS does not get one prefix — it gets
		// one PER DEVICE, and they are different strings. add_responsive_control()
		// refuses the single-control optimisation whenever `prefix_class` is set
		// (controls-stack.php:909), so these controls really are duplicated per
		// device, and each duplicate's prefix is sprintf'd with the device name:
		//
		//   'elementor%s-position-'  ->  desktop  elementor-position-
		//                                tablet   elementor-tablet-position-
		//                                mobile   elementor-mobile-position-
		//
		// Collapsing the variants and keeping only the base's prefix would throw
		// that away and leave the schema quietly claiming the tablet class is
		// `elementor-position-` too. Keep every device's real prefix.
		if ( ! empty( $r['prefix_class'] )
			&& ( $collapsed[ $base ]['prefix_class'] ?? null ) !== $r['prefix_class'] ) {
			$collapsed[ $base ]['prefix_class_devices'][ $matched_device ] = $r['prefix_class'];
		}
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
	// The module that registered it. Some modules are gated (see eh_module_gates),
	// and a widget from a gated module does not exist on an install where the gate
	// is shut. Recording the module is what lets a consumer say "this needs
	// WooCommerce" instead of "this widget works everywhere".
	$module = eh_module_of( $obj );
	if ( $module ) {
		$rec['module'] = $module;
	}
	// Elementor's bridge for legacy WP widgets. These exist ONLY because some
	// plugin (or WP core) registered a WP widget of that name — they are not part
	// of Elementor's own surface at all, and they differ from site to site.
	// Detected by class, not by the `wp-widget-` name prefix, which would be a
	// guess about a naming convention rather than a fact about the object.
	if ( class_exists( '\Elementor\Widget_WordPress' ) && $obj instanceof \Elementor\Widget_WordPress ) {
		$rec['wp_widget'] = true;
	}

	// ELEMENTOR V4 ATOMIC ELEMENTS ARE A SECOND DATA MODEL, NOT A THIRD KIND OF
	// WIDGET. `e-heading`, `e-button`, `e-flexbox`, the `e-form-*` set: they do not
	// use `get_controls()` at all — they declare a PROP SCHEMA, and their values are
	// type-tagged rather than plain:
	//
	//     classic:  "header_size": "h2"
	//     atomic:   "tag": { "$$type": "string", "value": "h2" }
	//
	// and their styling lives in a separate `styles` array, not in `settings`.
	//
	// So get_controls() returns an EMPTY array for them, and a schema that just
	// records that ships 21 widgets which appear to exist and appear to have no
	// settings. Both halves of that are false. Capture the real prop schema and say
	// plainly which system the widget belongs to.
	if ( method_exists( $obj, 'get_props_schema' ) ) {
		$rec['control_system'] = 'v4-atomic';
		$props = [];
		try {
			foreach ( $obj::get_props_schema() as $pname => $prop ) {
				$p = [ 'name' => $pname ];
				if ( method_exists( $prop, 'get_type' ) ) {
					$p['type'] = $prop->get_type();
				}
				if ( method_exists( $prop, 'get_default' ) ) {
					$p['default'] = $prop->get_default();
				}
				$props[] = $p;
			}
		} catch ( \Throwable $e ) {
			$rec['props_error'] = $e->getMessage();
		}
		$rec['props'] = $props;
	}
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

	// Some controls carry their allowed values on the CONTROL CLASS, not in the
	// control's args — so the per-control `options` we capture elsewhere is empty
	// and the schema ends up with nothing to say about what is legal. The entrance
	// and hover animations are the ones that matter: `_animation` and
	// `hover_animation` are on every widget, and their values are camelCase CSS
	// animation names from Animate.css (`fadeInUp`), not the kebab-case you would
	// guess. Writing `fade-in-up` stores fine and animates nothing.
	//
	// The lists are grouped ('Fading' => [ 'fadeIn' => 'Fade In', ... ]), so flatten
	// them; the group headings are editor UI, not values.
	if ( method_exists( $ctrl, 'get_animations' ) ) {
		$flat = [];
		foreach ( (array) $ctrl::get_animations() as $group => $items ) {
			if ( is_array( $items ) ) {
				foreach ( array_keys( $items ) as $k ) {
					$flat[] = (string) $k;
				}
			} else {
				$flat[] = (string) $group;
			}
		}
		if ( $flat ) {
			$entry['options'] = array_values( array_unique( $flat ) );
		}
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

// CANARY 3 — the class-emitting surface. `icon-box/position` is the reference
// case for BOTH of the things a naive extractor drops on the floor: its prefix is
// per-device (`elementor%s-position-`) and its stored value is remapped through a
// `classes_dictionary` before it becomes a class. Lose either and the schema still
// looks complete while telling you the tablet class is `elementor-position-` (it
// is not) and that `top` is an invalid option (it is not).
$cls_ok = false;
foreach ( $widgets['icon-box']['controls'] ?? [] as $c ) {
	if ( $c['name'] !== 'position' ) {
		continue;
	}
	$cls_ok = ( ( $c['prefix_class_devices']['tablet'] ?? null ) === 'elementor-tablet-position-' )
		&& ! empty( $c['classes_dictionary'] );
	break;
}
if ( ! $cls_ok ) {
	fwrite( STDERR, "FATAL: canary failed — icon-box/position lost its per-device prefix_class or its\n" );
	fwrite( STDERR, "classes_dictionary. The class-emitting surface is not being captured. Refusing to emit.\n" );
	exit( 1 );
}

// ---------------------------------------------------------------------------
// 5. Dynamic tags — the `__dynamic__` surface.
//
// A control with `dynamic.active` can be BOUND instead of set: its value comes
// from a registered tag (post title, featured image, an ACF field, the cart
// total...) rendered at view time. Which tags a control accepts is matched by
// CATEGORY - a text control takes tags in the `text` category, a media control
// the `image` category - so without this list the schema can say a control is
// dynamic-capable but nothing about what it can be bound TO, what settings the
// binding takes (an ACF tag needs a `key`), or whether the tag itself is Pro.
// ---------------------------------------------------------------------------
$dynamic_tags = [];
if ( isset( $plugin->dynamic_tags ) ) {
	foreach ( $plugin->dynamic_tags->get_tags() as $tag_name => $cfg ) {
		$inst = null;
		if ( is_object( $cfg ) ) {
			$inst = $cfg;
		} elseif ( is_array( $cfg ) && is_object( $cfg['instance'] ?? null ) ) {
			$inst = $cfg['instance'];
		}
		if ( ! $inst ) {
			continue;
		}
		try {
			list( $tier, $source ) = eh_tier_of( $inst );
			$rec = [
				'name'       => $tag_name,
				'title'      => method_exists( $inst, 'get_title' ) ? $inst->get_title() : null,
				'group'      => method_exists( $inst, 'get_group' ) ? $inst->get_group() : null,
				'categories' => method_exists( $inst, 'get_categories' ) ? $inst->get_categories() : [],
				'tier'       => $tier,
			];
			if ( $source !== 'elementor-core' && $source !== 'elementor-pro' ) {
				$rec['source'] = $source;   // a third-party tag: say whose it is
			}
			// The tag's OWN settings - what goes inside `settings` in the binding.
			// An ACF field tag without its `key` renders nothing, silently.
			if ( method_exists( $inst, 'get_controls' ) ) {
				$tctrl = [];
				foreach ( $inst->get_controls() as $cname => $c ) {
					$t = $c['type'] ?? '';
					if ( in_array( $t, [ 'section', 'tab', 'tabs', 'heading', 'raw_html', 'divider' ], true ) ) {
						continue;
					}
					$e = [ 'name' => $cname, 'type' => $t ];
					$opts = eh_option_keys( $c );
					if ( $opts ) {
						$e['options'] = $opts;
					}
					if ( isset( $c['default'] ) && $c['default'] !== '' ) {
						$e['default'] = $c['default'];
					}
					$tctrl[] = $e;
				}
				if ( $tctrl ) {
					$rec['settings'] = $tctrl;
				}
			}
			$dynamic_tags[ $tag_name ] = $rec;
		} catch ( \Throwable $e ) {
			$dynamic_tags[ $tag_name ] = [ 'name' => $tag_name, 'error' => $e->getMessage() ];
		}
	}
}

// ---------------------------------------------------------------------------
// 5b. Theme Builder display conditions (Pro) — WHERE a template applies.
//
// The condition strings stored in a template's meta ('include/singular/post/123')
// are built from this registry. Without it the schema can describe the Display
// Conditions control but not one legal value of it.
// ---------------------------------------------------------------------------
$tb_conditions = null;
if ( class_exists( '\ElementorPro\Modules\ThemeBuilder\Module' ) ) {
	try {
		$cm = \ElementorPro\Modules\ThemeBuilder\Module::instance()->get_conditions_manager();
		if ( method_exists( $cm, 'get_conditions_config' ) ) {
			$tb_conditions = $cm->get_conditions_config();
		}
	} catch ( \Throwable $e ) {
		$tb_conditions = [ 'error' => $e->getMessage() ];
	}
}

// ---------------------------------------------------------------------------
// 5c. Documents — the page IS a settable surface too.
//
// Everything above describes what goes INSIDE `_elementor_data`. Three more
// surfaces sit beside it, and a headless builder that cannot reach them cannot
// even switch a page to the Canvas template:
//
//   document types    the legal values of `_elementor_template_type` (29 of them,
//                     install-dependent: popup/header/single need Pro, product
//                     needs WooCommerce)
//   page settings     `_elementor_page_settings` - hide_title, template (canvas /
//                     header-footer), per-page margin/padding/background/custom CSS
//   the Kit           `_elementor_page_settings` ON THE KIT POST - the entire Site
//                     Settings panel: global colors, global fonts, theme style,
//                     layout defaults, lightbox. `__globals__` references resolve
//                     into the repeaters registered here.
// ---------------------------------------------------------------------------
$documents = [];
foreach ( $plugin->documents->get_document_types() as $dtype => $dclass ) {
	$file = ( new ReflectionClass( $dclass ) )->getFileName();
	$file = str_replace( '\\', '/', (string) $file );
	$tier = strpos( $file, '/elementor-pro/' ) !== false ? 'pro' : 'free';
	$rec  = [ 'type' => $dtype, 'class' => $dclass, 'tier' => $tier ];
	if ( preg_match( '#/modules/([^/]+)/#', $file, $m ) ) {
		$rec['module'] = $m[1];
	}
	$documents[ $dtype ] = $rec;
}

/** Describe a document's SETTINGS stack with the same record shape as widgets. */
function eh_document_settings( $doc, $device_suffixes, &$anomalies, $label ) {
	$raw = [];
	$sections = [];
	foreach ( $doc->get_controls() as $cname => $ctrl ) {
		if ( ( $ctrl['type'] ?? '' ) === \Elementor\Controls_Manager::SECTION ) {
			$sections[] = [
				'name'  => $cname,
				'label' => is_string( $ctrl['label'] ?? null ) ? $ctrl['label'] : null,
				'tab'   => $ctrl['tab'] ?? null,
			];
			continue;
		}
		if ( in_array( $ctrl['type'] ?? '', [ 'tab', 'tabs', 'divider', 'heading', 'raw_html', 'notice', 'alert', 'deprecated_notice' ], true ) ) {
			continue;
		}
		$raw[] = eh_control_record( $cname, $ctrl );
	}
	return [
		'controls' => eh_collapse_responsive( $raw, $device_suffixes, $anomalies, $label ),
		'sections' => $sections,
	];
}

$page_settings = [];
// Any published page/post does: the settings stack is a property of the document
// TYPE, not of the particular post.
$any_page = get_posts( [ 'post_type' => 'page', 'post_status' => 'publish', 'numberposts' => 1, 'fields' => 'ids' ] );
if ( $any_page ) {
	$doc = $plugin->documents->get( $any_page[0] );
	if ( $doc ) {
		$page_settings['wp-page'] = eh_document_settings( $doc, $device_suffixes, $anomalies, 'doc:wp-page' );
	}
}
$any_post = get_posts( [ 'post_type' => 'post', 'post_status' => 'publish', 'numberposts' => 1, 'fields' => 'ids' ] );
if ( $any_post ) {
	$doc = $plugin->documents->get( $any_post[0] );
	if ( $doc ) {
		$page_settings['wp-post'] = eh_document_settings( $doc, $device_suffixes, $anomalies, 'doc:wp-post' );
	}
}

// Popups (Pro): the display surface - triggers (on load / scroll / click / exit
// intent), timing rules, advanced rules - is the popup DOCUMENT's own settings
// stack, plus its layout (width, position, overlay, close button). It needs a
// popup post to instantiate against; the extractor USES one if the site has one
// and says so if not, rather than creating posts on someone's site as a side
// effect.
$popup_settings = null;
if ( isset( $documents['popup'] ) ) {
	$popup_posts = get_posts( [
		'post_type'   => 'elementor_library',
		'post_status' => [ 'publish', 'draft' ],
		'numberposts' => 1,
		'fields'      => 'ids',
		'meta_key'    => '_elementor_template_type',
		'meta_value'  => 'popup',
	] );
	if ( $popup_posts ) {
		$doc = $plugin->documents->get( $popup_posts[0] );
		if ( $doc ) {
			$popup_settings = eh_document_settings( $doc, $device_suffixes, $anomalies, 'doc:popup' );
			$popup_settings['note'] =
				'The popup document settings: layout (width/height/position), style '
				. '(overlay, close button), and under advanced the OPEN rules. Triggers '
				. 'and timing are saved separately in _elementor_popup_display_settings '
				. 'meta as {"triggers":{...},"timing":{...}} - the editor writes both.';
		}
	} else {
		$popup_settings = [ 'note' => 'no popup exists on the extraction site; create one draft popup and re-extract to capture this surface' ];
	}
}

$kit_settings = null;
try {
	$kit = $plugin->kits_manager->get_active_kit();
	if ( $kit && $kit->get_id() ) {
		$kit_settings = eh_document_settings( $kit, $device_suffixes, $anomalies, 'doc:kit' );
		$kit_settings['note'] =
			'The Site Settings panel. Saved as _elementor_page_settings on the KIT post '
			. '(option elementor_active_kit holds its id). Global colors live in the '
			. 'system_colors / custom_colors repeaters, global fonts in system_typography / '
			. 'custom_typography; a __globals__ reference like globals/colors?id=primary '
			. 'resolves to the repeater item whose _id matches. After editing the kit, '
			. 'regenerate CSS for the SITE, not one post: wp elementor flush-css.';
	}
} catch ( \Throwable $e ) {
	$kit_settings = [ 'error' => $e->getMessage() ];
}

// ---------------------------------------------------------------------------
// 5d. Emit.
// ---------------------------------------------------------------------------
// THE SURFACE IS A PROPERTY OF THE INSTALL, NOT OF ELEMENTOR. Record what was true
// of the machine this ran on, so a consumer can tell "Elementor has no such widget"
// apart from "this schema was taken somewhere that could not see it".
$gates = eh_module_gates();
$shut  = array_keys( array_filter( $gates, function ( $g ) { return $g['active'] === false; } ) );

$experiments = [];
if ( isset( \Elementor\Plugin::$instance->experiments ) ) {
	foreach ( \Elementor\Plugin::$instance->experiments->get_features() as $fname => $f ) {
		$experiments[ $fname ] =
			\Elementor\Plugin::$instance->experiments->is_feature_active( $fname );
	}
}

$out = [
	'meta' => [
		'elementor_version'     => defined( 'ELEMENTOR_VERSION' ) ? ELEMENTOR_VERSION : null,
		'elementor_pro_version' => defined( 'ELEMENTOR_PRO_VERSION' ) ? ELEMENTOR_PRO_VERSION : null,
		'php_version'           => PHP_VERSION,
		'scope'                 => $scope,
		'extracted_at'          => gmdate( 'Y-m-d' ),
		'control_optimisation_disabled' => true,
		'third_party_skipped'   => $skipped,
		// Every Elementor Pro module whose loading is CONDITIONAL, its gate as
		// written in Elementor's source, and whether that gate was open here. A
		// module that did not load registered no widgets, and its widgets are
		// therefore absent from this file - not from Elementor.
		'module_gates'          => $gates,
		'modules_shut'          => $shut,
		'woocommerce_active'    => class_exists( 'woocommerce' ),
		'experiments'           => $experiments,
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
	'dynamic_tags'   => $dynamic_tags,
	'theme_builder_conditions' => $tb_conditions,
	'documents'      => $documents,
	'page_settings'  => $page_settings,
	'popup_settings' => $popup_settings,
	'kit_settings'   => $kit_settings,
	'elements'       => $elements,
	'widgets'        => $widgets,
];

echo json_encode( $out, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
