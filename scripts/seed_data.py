"""
Seed data generator — creates 50,000 realistic e-commerce orders.

Generates:
  - 1,000 customers (10 countries, realistic names)
  - 200 products (8 categories, realistic prices)
  - 50,000 orders over the last 2 years
  - 80,000+ order items

Usage:
    pip install faker psycopg2-binary
    python scripts/seed_data.py
    python scripts/seed_data.py --orders 10000  # smaller dataset
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import date, timedelta

import psycopg2
from faker import Faker

fake = Faker()
random.seed(42)
Faker.seed(42)

# ── Config ─────────────────────────────────────────────────────────────────

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ecommerce_user:changeme@localhost:5432/ecommerce_db",
)

CATEGORIES = {
    "Electronics":   [("Laptop", 800, 1800), ("Phone", 300, 900), ("Tablet", 250, 700),
                      ("Headphones", 50, 350), ("Smartwatch", 150, 500)],
    "Clothing":      [("T-Shirt", 15, 60), ("Jeans", 40, 120), ("Dress", 45, 200),
                      ("Jacket", 60, 250), ("Shoes", 50, 200)],
    "Home & Kitchen":[("Coffee Maker", 30, 200), ("Blender", 25, 150), ("Toaster", 20, 80),
                      ("Pan Set", 40, 200), ("Knife Set", 30, 150)],
    "Sports":        [("Yoga Mat", 20, 80), ("Running Shoes", 60, 200), ("Dumbbell Set", 50, 200),
                      ("Water Bottle", 15, 50), ("Resistance Bands", 10, 40)],
    "Books":         [("Fiction Novel", 8, 25), ("Cookbook", 15, 45), ("Self-Help", 10, 30),
                      ("Tech Manual", 25, 80), ("Children Book", 8, 20)],
    "Beauty":        [("Moisturiser", 20, 80), ("Serum", 25, 120), ("Lipstick", 10, 50),
                      ("Perfume", 40, 200), ("Sunscreen", 15, 60)],
    "Toys":          [("LEGO Set", 25, 150), ("Board Game", 20, 60), ("Puzzle", 15, 40),
                      ("Action Figure", 10, 50), ("Stuffed Animal", 12, 45)],
    "Food":          [("Coffee Beans", 12, 40), ("Olive Oil", 10, 35), ("Protein Powder", 30, 80),
                      ("Tea Set", 15, 60), ("Chocolate Box", 10, 40)],
}

COUNTRIES = ["US", "GB", "CA", "AU", "DE", "FR", "IN", "BR", "JP", "MX"]
COUNTRY_WEIGHTS = [40, 15, 10, 8, 8, 6, 5, 3, 3, 2]
STATUSES = ["delivered", "delivered", "delivered", "shipped", "confirmed", "cancelled", "refunded"]
PAYMENT_METHODS = ["credit_card", "credit_card", "credit_card", "paypal", "debit_card", "bank_transfer"]


def seed(n_orders: int = 50_000) -> None:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("Seeding customers...")
    customer_ids = []
    for _ in range(1_000):
        country = random.choices(COUNTRIES, weights=COUNTRY_WEIGHTS)[0]
        signup = fake.date_between(start_date="-3y", end_date="today")
        cur.execute(
            """
            INSERT INTO customers (email, first_name, last_name, country, city, signup_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING customer_id
            """,
            (fake.unique.email(), fake.first_name(), fake.last_name(),
             country, fake.city(), signup),
        )
        row = cur.fetchone()
        if row:
            customer_ids.append(row[0])
    conn.commit()
    print(f"  {len(customer_ids)} customers created")

    print("Seeding products...")
    product_ids = []
    for category, items in CATEGORIES.items():
        for name, min_price, max_price in items:
            price = round(random.uniform(min_price, max_price), 2)
            cost = round(price * random.uniform(0.3, 0.6), 2)
            sku = f"{category[:3].upper()}-{fake.unique.bothify('???-####').upper()}"
            cur.execute(
                """
                INSERT INTO products (sku, name, category, price, cost)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (sku) DO NOTHING
                RETURNING product_id
                """,
                (sku, f"{fake.word().title()} {name}", category, price, cost),
            )
            row = cur.fetchone()
            if row:
                product_ids.append((row[0], price))
    conn.commit()
    print(f"  {len(product_ids)} products created")

    print(f"Seeding {n_orders} orders...")
    batch_size = 500
    total_items = 0

    for batch_start in range(0, n_orders, batch_size):
        orders_batch = []
        for _ in range(min(batch_size, n_orders - batch_start)):
            customer_id = random.choice(customer_ids)
            order_date = fake.date_between(start_date="-2y", end_date="today")
            status = random.choice(STATUSES)
            n_items = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5])[0]
            items = random.sample(product_ids, min(n_items, len(product_ids)))

            total = 0.0
            item_rows = []
            for pid, price in items:
                qty = random.randint(1, 3)
                discount_pct = random.choices([0, 5, 10, 15, 20], weights=[50, 20, 15, 10, 5])[0]
                line_total = price * qty * (1 - discount_pct / 100)
                total += line_total
                item_rows.append((pid, qty, round(price, 2), discount_pct))

            discount = round(total * random.uniform(0, 0.05), 2)
            shipping = 0.0 if total > 50 else round(random.uniform(4.99, 12.99), 2)
            total = round(total - discount + shipping, 2)

            shipped = None
            delivered = None
            if status in ("shipped", "delivered"):
                shipped = order_date + timedelta(days=random.randint(1, 5))
            if status == "delivered":
                delivered = shipped + timedelta(days=random.randint(2, 10))

            cur.execute(
                """
                INSERT INTO orders
                    (customer_id, status, total_amount, discount_amount,
                     shipping_amount, currency, payment_method, order_date,
                     shipped_date, delivered_date)
                VALUES (%s,%s,%s,%s,%s,'USD',%s,%s,%s,%s)
                RETURNING order_id
                """,
                (customer_id, status, total, discount, shipping,
                 random.choice(PAYMENT_METHODS), order_date, shipped, delivered),
            )
            order_id = cur.fetchone()[0]

            for pid, qty, unit_price, discount_pct in item_rows:
                cur.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount_pct) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (order_id, pid, qty, unit_price, discount_pct),
                )
                total_items += 1

        conn.commit()
        print(f"  {batch_start + batch_size:>6,} / {n_orders:,} orders", end="\r")

    print(f"\n  {n_orders:,} orders + {total_items:,} order items created")

    cur.close()
    conn.close()
    print("\nSeed complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--orders", type=int, default=50_000)
    args = parser.parse_args()
    seed(args.orders)
