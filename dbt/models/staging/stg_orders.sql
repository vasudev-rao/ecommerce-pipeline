-- models/staging/stg_orders.sql
-- Staging view: clean and rename raw orders columns.
-- One row per order_id. No aggregation here — just standardise.

{{ config(materialized='view') }}

with source as (
    select * from {{ source('ecommerce_raw', 'orders') }}
),

renamed as (
    select
        order_id,
        customer_id,
        status,
        total_amount,
        discount_amount,
        shipping_amount,
        currency,
        payment_method,
        order_date,
        shipped_date,
        delivered_date,
        customer_country,

        -- Computed
        revenue_net,
        is_high_value,
        day_of_week,
        week_of_year,
        month,
        quarter,
        year,
        is_weekend,

        -- Lineage
        run_id,
        cleaned_at,

        -- Derived
        total_amount - discount_amount                as net_revenue,
        date_diff(delivered_date, order_date, day)    as days_to_deliver,
        case
            when status = 'delivered'  then true
            else false
        end as is_completed

    from source
    where order_id is not null
)

select * from renamed
