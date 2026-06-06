# Metabase Dashboard Setup

## 1. Start Metabase

```bash
make docker-up
# Open http://localhost:3000
# Follow the setup wizard
```

## 2. Connect BigQuery

1. Go to **Settings → Admin → Databases → Add database**
2. Select **BigQuery**
3. Enter:
   - **Project ID**: your GCP project ID
   - **Service account key**: upload your `service-account.json`
   - **Dataset filters**: `ecommerce_mart` (show only mart tables)
4. Click **Save**

Alternatively connect the local PostgreSQL for testing:
- **Host**: `source-db` (if running inside Docker) or `localhost`
- **Port**: `5432`
- **Database**: `ecommerce_db`
- **User/Password**: `ecommerce_user / changeme`

## 3. Recommended questions to build

### Revenue dashboard
```sql
-- Daily revenue trend (last 30 days)
SELECT order_date, SUM(net_revenue) AS revenue
FROM ecommerce_mart.daily_revenue
WHERE order_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY order_date
ORDER BY order_date
```

```sql
-- Revenue by category (current month)
SELECT category, SUM(gross_revenue) AS revenue, SUM(order_count) AS orders
FROM ecommerce_mart.daily_revenue
WHERE DATE_TRUNC(order_date, MONTH) = DATE_TRUNC(CURRENT_DATE(), MONTH)
GROUP BY category
ORDER BY revenue DESC
```

### Customer dashboard
```sql
-- Customer segment breakdown
SELECT customer_segment, COUNT(*) AS customers, AVG(lifetime_value) AS avg_ltv
FROM ecommerce_raw.customers
GROUP BY customer_segment
```

```sql
-- Month-1 retention by cohort
SELECT cohort_month, retention_rate_pct
FROM ecommerce_mart.customer_retention
WHERE months_since_signup = 1
ORDER BY cohort_month
```

### Product dashboard
```sql
-- Top 10 products by revenue
SELECT product_name, category, total_revenue, units_sold, refund_rate_pct
FROM ecommerce_mart.top_products
ORDER BY total_revenue DESC
LIMIT 10
```

## 4. Build a simple dashboard

In Metabase:
1. Create the 3 SQL questions above
2. Click **New → Dashboard**
3. Add all 3 questions
4. Add a date filter connected to `order_date`
5. Share the dashboard link

That's it — a working BI dashboard in under 30 minutes.
