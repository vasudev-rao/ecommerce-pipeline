-- models/staging/stg_customers.sql
{{ config(materialized='view') }}

with source as (
    select * from {{ source('ecommerce_raw', 'customers') }}
)

select
    customer_id,
    email,
    first_name,
    last_name,
    first_name || ' ' || last_name  as full_name,
    country,
    city,
    signup_date,
    is_active,
    customer_segment,
    order_count,
    lifetime_value,
    days_since_signup,
    run_id
from source
where customer_id is not null
  and email is not null
