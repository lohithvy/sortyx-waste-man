# Sortyx 2.0 — Database Schema

## Supabase Project

| Property | Value |
|----------|-------|
| Project ID | `plecqogpksvobfmdrlrn` |
| Organization | Sortyx Waste Management |
| Region | ap-south-1 |
| RLS | Enabled on all tables |
| Access | Service-role key (backend only) |

> ⚠️ **Do not recreate, delete, or destructively modify these tables.**

---

## Tables

### `devices`

Tracks connected Sortyx devices.

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | Device unique identifier |
| `device_code` | text | Short device code |
| `display_name` | text | Human-readable name |
| `status` | text | Connection status |
| `firmware_version` | text | Software version |
| `last_seen_at` | timestamptz | Last heartbeat |
| `created_at` | timestamptz | Record creation |
| `updated_at` | timestamptz | Last update |

### `bins`

Three bin records: `bio`, `organic`, `non_bio`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | Bin unique identifier |
| `category` | text | `bio`, `organic`, or `non_bio` |
| `display_name` | text | "Bio", "Organic", "Non-Bio" |
| `fill_percentage` | numeric | Current fill level (0-100) |
| `distance_cm` | numeric | Latest ultrasonic reading (cm) |
| `empty_distance_cm` | numeric | Calibrated empty distance |
| `full_distance_cm` | numeric | Calibrated full distance |
| `sensor_status` | text | `online`, `offline`, `error`, `not_configured` |
| `last_read_at` | timestamptz | Last sensor reading time |
| `created_at` | timestamptz | Record creation |
| `updated_at` | timestamptz | Last update |

### `sorting_events`

Records every sorting operation.

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | Event unique identifier |
| `device_id` | uuid (FK) | Reference to `devices.id` |
| `bin_id` | uuid (FK) | Reference to `bins.id` |
| `waste_name` | text | Detected waste name |
| `category` | text | `bio`, `organic`, or `non_bio` |
| `confidence` | numeric | AI confidence (0.0-1.0) |
| `classification_status` | text | `classified`, `rejected`, `failed`, etc. |
| `sorting_status` | text | `pending`, `completed`, `failed`, etc. |
| `classification_model` | text | Gemini model used |
| `decision_reason` | text | AI reasoning |
| `created_at` | timestamptz | Event creation |
| `updated_at` | timestamptz | Last status update |

### `sensor_readings`

Historical sensor data for each bin.

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid (PK) | Reading unique identifier |
| `bin_id` | uuid (FK) | Reference to `bins.id` |
| `distance_cm` | numeric | Measured distance (cm) |
| `fill_percentage` | numeric | Calculated fill level (0-100) |
| `sensor_status` | text | Sensor status at reading time |
| `recorded_at` | timestamptz | Reading timestamp |

---

## Query Patterns

### Today's Statistics (IST)

```sql
SELECT
    COUNT(*) FILTER (WHERE sorting_status = 'completed') AS total_items,
    COUNT(*) FILTER (WHERE sorting_status = 'completed' AND category = 'organic') AS organic,
    COUNT(*) FILTER (WHERE sorting_status = 'completed' AND category = 'bio') AS bio,
    COUNT(*) FILTER (WHERE sorting_status = 'completed' AND category = 'non_bio') AS non_bio
FROM sorting_events
WHERE created_at >= (NOW() AT TIME ZONE 'Asia/Kolkata')::date AT TIME ZONE 'Asia/Kolkata'
  AND created_at < ((NOW() AT TIME ZONE 'Asia/Kolkata')::date + INTERVAL '1 day') AT TIME ZONE 'Asia/Kolkata';
```

### Bin Status

```sql
SELECT category, display_name, fill_percentage, distance_cm, sensor_status, last_read_at
FROM bins
ORDER BY category;
```

### Record Sorting Event

```sql
INSERT INTO sorting_events (device_id, bin_id, waste_name, category, confidence,
    classification_status, sorting_status, classification_model, decision_reason)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
RETURNING id;
```

---

## Data Integrity Rules

1. Only `sorting_status = 'completed'` events count in daily statistics.
2. Failed, uncertain, and manually reviewed events are kept for auditing.
3. No images are stored in the database (strictly in-memory temporary buffers).
4. No fake weights or simulated readings in production — unconfigured sensors report `None` / `not_configured`.
5. All timestamps are `timestamptz` (stored in UTC, evaluated for calendar day in IST).
6. Idempotent event deduplication: Client generates UUID4 at creation; offline retries use `upsert(..., on_conflict="id")` guaranteeing zero duplicate rows.
7. Resilient offline queue with bounded exponential backoff (5.0s to 60.0s) ensures no data loss during network disconnections.

