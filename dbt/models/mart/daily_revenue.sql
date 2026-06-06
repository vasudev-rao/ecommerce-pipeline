-- models/mart/daily_revenue.sql
-- Daily revenue summary — powers the main business dashboard.
-- Grain: one row per (order_date, category, country).

{{ config(materialized='table', partition_by={'field': 'order_date', 'data_type': 'date'}) }}

with orders as (
    select * from {{ ref('stg_orders') }}
),

items as (
    select
        oi.order_id,
        p.category,
        sum(oi.line_total) as category_revenue
    from {{ source('ecommerce_raw', 'order_items') }} oi
    join {{ source('ecommerce_raw', 'products') }} p
        on oi.product_id = p.product_id
    group by 1, 2
),

daily as (
    select
        o.order_date,
        o.customer_country                           as country,
        coalesce(i.category, 'Unknown')              as category,

        -- Volume
        count(distinct o.order_id)                   as order_count,
        count(distinct o.customer_id)                as unique_customers,

        -- Revenue
        sum(o.total_amount)                          as gross_revenue,
        sum(o.discount_amount)                       as total_discounts,
        sum(o.shipping_amount)                       as total_shipping,
        sum(o.net_revenue)                           as net_revenue,
        avg(o.total_amount)                          as avg_order_value,

        -- Status breakdown
        countif(o.status = 'delivered')              as delivered_count,
        countif(o.status = 'cancelled')              as cancelled_count,
        countif(o.status = 'refunded')               as refunded_count,

        -- High value
        countif(o.is_high_value)                     as high_value_order_count,

        -- Payment
        countif(o.payment_method = 'credit_card')    as credit_card_count,
        countif(o.payment_method = 'paypal')         as paypal_count,

        -- Weekend
        countif(o.is_weekend)                        as weekend_order_count

    from orders o
    left join items i on o.order_id = i.order_id
    group by 1, 2, 3
)

select
    *,
    safe_divide(cancelled_count, order_count)        as cancellation_rate,
    safe_divide(refunded_count, order_count)         as refund_rate,
    safe_divide(total_discounts, gross_revenue)      as discount_rate
from daily
