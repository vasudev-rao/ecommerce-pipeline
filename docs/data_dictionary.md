# Data Dictionary — E-Commerce Pipeline

## Source tables (PostgreSQL)

### customers
| Column | Type | Description |
|---|---|---|
| customer_id | SERIAL | Primary key |
| email | VARCHAR(255) | Unique email address |
| first_name | VARCHAR(100) | First name |
| last_name | VARCHAR(100) | Last name |
| country | VARCHAR(2) | ISO-3166 2-letter country code |
| city | VARCHAR(100) | City name |
| signup_date | DATE | Date customer registered |
| is_active | BOOLEAN | Whether account is active |
| updated_at | TIMESTAMPTZ | Last modified — used as watermark |

### products
| Column | Type | Description |
|---|---|---|
| product_id | SERIAL | Primary key |
| sku | VARCHAR(50) | Stock keeping unit — unique |
| name | VARCHAR(255) | Product display name |
| category | VARCHAR(100) | Top-level category (Electronics, Clothing, etc.) |
| price | NUMERIC(10,2) | Selling price in USD |
| cost | NUMERIC(10,2) | Cost to the business in USD |
| is_active | BOOLEAN | Whether product is currently sold |

### orders
| Column | Type | Description |
|---|---|---|
| order_id | SERIAL | Primary key |
| customer_id | INTEGER | FK → customers |
| status | VARCHAR(20) | pending · confirmed · shipped · delivered · cancelled · refunded |
| total_amount | NUMERIC(10,2) | Gross order total including shipping |
| discount_amount | NUMERIC(10,2) | Total discount applied |
| shipping_amount | NUMERIC(10,2) | Shipping fee |
| currency | VARCHAR(3) | ISO-4217 currency code |
| payment_method | VARCHAR(50) | credit_card · paypal · debit_card · bank_transfer |
| order_date | DATE | Date order was placed |
| shipped_date | DATE | Date order was shipped (nullable) |
| delivered_date | DATE | Date order was delivered (nullable) |
| updated_at | TIMESTAMPTZ | Last modified — used as watermark |

### order_items
| Column | Type | Description |
|---|---|---|
| item_id | SERIAL | Primary key |
| order_id | INTEGER | FK → orders |
| product_id | INTEGER | FK → products |
| quantity | INTEGER | Units ordered (always > 0) |
| unit_price | NUMERIC(10,2) | Price at time of purchase |
| discount_pct | NUMERIC(5,2) | Line-item discount percentage (0–100) |

---

## Enriched columns (added by pipeline)

### orders (after enrich stage)
| Column | Type | Description |
|---|---|---|
| revenue_net | FLOAT | total_amount − discount_amount |
| is_high_value | BOOLEAN | True if total_amount > $200 |
| day_of_week | STRING | Monday · Tuesday · … |
| week_of_year | INTEGER | ISO week number (1–53) |
| month | INTEGER | Month number (1–12) |
| quarter | INTEGER | Quarter (1–4) |
| year | INTEGER | Year |
| is_weekend | BOOLEAN | True if Saturday or Sunday |
| run_id | STRING | Pipeline run identifier |

### customers (after enrich stage)
| Column | Type | Description |
|---|---|---|
| customer_segment | STRING | new · returning · loyal |
| order_count | INTEGER | Lifetime delivered orders |
| lifetime_value | FLOAT | Sum of delivered order totals |
| days_since_signup | INTEGER | Days since signup_date |

**Segment rules:**
- `new` — 0–1 delivered orders
- `returning` — 2–4 delivered orders
- `loyal` — 5+ delivered orders

### products (after enrich stage)
| Column | Type | Description |
|---|---|---|
| margin_pct | FLOAT | (price − cost) / price × 100 |
| price_tier | STRING | budget (<$30) · mid ($30–$100) · premium (>$100) |
| margin_tier | STRING | low (<30%) · standard (30–60%) · high (>60%) |

---

## Mart tables (BigQuery)

### mart.daily_revenue
Grain: one row per (order_date, country, category)

| Column | Type | Description |
|---|---|---|
| order_date | DATE | Aggregation date |
| country | STRING | Customer country |
| category | STRING | Product category |
| order_count | INTEGER | Total orders |
| unique_customers | INTEGER | Distinct customers |
| gross_revenue | FLOAT | Sum of total_amount |
| total_discounts | FLOAT | Sum of discount_amount |
| net_revenue | FLOAT | gross_revenue − total_discounts |
| avg_order_value | FLOAT | Mean order total |
| delivered_count | INTEGER | Delivered orders |
| cancelled_count | INTEGER | Cancelled orders |
| cancellation_rate | FLOAT | cancelled / total (0.0–1.0) |
| refund_rate | FLOAT | refunded / total (0.0–1.0) |
| discount_rate | FLOAT | discounts / gross_revenue |

### mart.customer_retention
Grain: one row per (cohort_month, activity_month)

| Column | Type | Description |
|---|---|---|
| cohort_month | DATE | Month customer first signed up |
| activity_month | DATE | Month of the activity being measured |
| months_since_signup | INTEGER | Months between cohort and activity |
| active_customers | INTEGER | Customers with a delivered order this month |
| cohort_size | INTEGER | Total customers in the cohort |
| retention_rate_pct | FLOAT | active / cohort_size × 100 |

### mart.top_products
Grain: one row per product_id

| Column | Type | Description |
|---|---|---|
| product_id | INTEGER | Product identifier |
| product_name | STRING | Display name |
| category | STRING | Product category |
| price_tier | STRING | budget · mid · premium |
| total_revenue | FLOAT | Sum of delivered line totals |
| units_sold | INTEGER | Count of delivered orders containing this product |
| quantity_sold | INTEGER | Total units delivered |
| avg_selling_price | FLOAT | Average actual selling price |
| refund_rate_pct | FLOAT | refunded / (delivered + refunded) × 100 |
| total_gross_profit | FLOAT | revenue − (cost × quantity) |
| last_sold_date | DATE | Most recent delivered order date |
