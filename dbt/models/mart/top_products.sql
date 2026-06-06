-- models/mart/top_products.sql
-- Product performance — revenue, units sold, return rate per product.
-- Grain: one row per product_id.

{{ config(materialized='table') }}

with items as (
    select
        oi.product_id,
        p.name            as product_name,
        p.category,
        p.price_tier,
        p.margin_pct,
        p.price           as unit_price,
        p.cost            as unit_cost,
        oi.quantity,
        oi.unit_price     as sold_price,
        oi.line_total,
        o.status,
        o.order_date
    from {{ source('ecommerce_raw', 'order_items') }} oi
    join {{ source('ecommerce_raw', 'products') }}    p  on oi.product_id = p.product_id
    join {{ source('ecommerce_raw', 'orders') }}      o  on oi.order_id   = o.order_id
)

select
    product_id,
    product_name,
    category,
    price_tier,
    unit_price,
    unit_cost,
    margin_pct,

    -- Sales volume
    countif(status = 'delivered')               as units_sold,
    sum(case when status = 'delivered'
             then quantity end)                 as quantity_sold,
    sum(case when status = 'delivered'
             then line_total end)               as total_revenue,
    avg(case when status = 'delivered'
             then sold_price end)               as avg_selling_price,

    -- Returns & cancellations
    countif(status = 'refunded')                as refund_count,
    countif(status = 'cancelled')               as cancel_count,
    round(countif(status = 'refunded')
        / nullif(countif(status in ('delivered','refunded')), 0) * 100, 2) as refund_rate_pct,

    -- Profitability
    sum(case when status = 'delivered'
             then line_total - (unit_cost * quantity) end) as total_gross_profit,

    -- Recency
    max(order_date)                             as last_sold_date,
    min(order_date)                             as first_sold_date

from items
group by 1,2,3,4,5,6,7
order by total_revenue desc
