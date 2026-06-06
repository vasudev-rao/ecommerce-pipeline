-- models/mart/customer_retention.sql
-- Monthly cohort retention — what % of customers from month X are still buying in month Y.
-- Grain: one row per (cohort_month, activity_month).

{{ config(materialized='table') }}

with customer_orders as (
    select
        o.customer_id,
        date_trunc(c.signup_date, month)                         as cohort_month,
        date_trunc(o.order_date, month)                         as activity_month
    from {{ ref('stg_orders') }} o
    join {{ ref('stg_customers') }} c
        on o.customer_id = c.customer_id
    where o.status = 'delivered'
),

cohort_sizes as (
    select
        cohort_month,
        count(distinct customer_id)  as cohort_size
    from customer_orders
    group by 1
),

monthly_active as (
    select
        cohort_month,
        activity_month,
        count(distinct customer_id)  as active_customers,
        date_diff(activity_month, cohort_month, month) as months_since_signup
    from customer_orders
    group by 1, 2
)

select
    ma.cohort_month,
    ma.activity_month,
    ma.months_since_signup,
    ma.active_customers,
    cs.cohort_size,
    round(ma.active_customers / cs.cohort_size * 100, 2) as retention_rate_pct
from monthly_active ma
join cohort_sizes cs on ma.cohort_month = cs.cohort_month
order by 1, 3
