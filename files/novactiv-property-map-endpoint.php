<?php
/**
 * Plugin Name: Novactiv Property Map Endpoint
 * Description: Exposes published property links keyed by QuickDeal object id.
 */

if (!defined('ABSPATH')) {
    exit;
}

add_action('rest_api_init', function () {
    register_rest_route('novactiv/v1', '/property-map', [
        'methods' => 'GET',
        'callback' => 'novactiv_property_map_endpoint',
        'permission_callback' => '__return_true',
    ]);
});

function novactiv_property_map_endpoint(WP_REST_Request $request): WP_REST_Response
{
    global $wpdb;

    $rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT pm.meta_value AS qd_id, p.ID AS post_id
             FROM {$wpdb->postmeta} pm
             INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
             WHERE pm.meta_key = %s
               AND pm.meta_value <> ''
               AND p.post_type = %s
               AND p.post_status = %s",
            '_property_qd_id',
            'property',
            'publish'
        ),
        ARRAY_A
    );

    $map = [];
    foreach ($rows as $row) {
        $qd_id = trim((string) $row['qd_id']);
        if ($qd_id === '') {
            continue;
        }
        $map[$qd_id] = get_permalink((int) $row['post_id']);
    }

    return new WP_REST_Response([
        'count' => count($map),
        'items' => $map,
    ]);
}
