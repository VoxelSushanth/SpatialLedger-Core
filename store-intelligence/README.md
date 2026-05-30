# Store Intelligence System — Purplle Tech Challenge 2026

## Quick Start (under 5 minutes)

```bash
git clone <your-repo>
cd store-intelligence
cp .env.example .env

# Option A: With CCTV footage
cp /path/to/your/video.mp4 data/videos/
cp /path/to/sales_ground_truth.csv data/

# Option B: Without footage (simulation mode — still fully functional)
# Just run — simulation mode auto-activates

docker compose up --build
```

**API available at:** http://localhost:8000  
**Dashboard at:** http://localhost:3000  
**API docs at:** http://localhost:8000/docs

## Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics` | GET | Full store analytics with footfall, conversion, dwell time, revenue |
| `/funnel` | GET | Customer conversion funnel from entry to purchase |
| `/anomalies` | GET | Detected anomalies (crowd surge, dwell outliers, low conversion) |
| `/zones` | GET | Per-zone metrics and current occupancy heatmap |
| `/events` | GET/POST | Raw event stream with pagination; POST for manual injection |
| `/health` | GET | Health check endpoint |
| `/ready` | GET | Readiness check (validates DB + Redis connectivity) |
| `/ws/live` | WebSocket | Real-time event feed for dashboard updates |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Video     │────▶│  Ingestion    │────▶│   Redis     │────▶│  Consumer   │────▶│ PostgreSQL  │
│   Input     │     │  (YOLO+Track) │     │   Streams   │     │  (Sessions) │     │  (Persist)  │
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                  │
                                                                  ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│  Dashboard  │◀────│   FastAPI     │◀────│   Redis     │◀────│   Events    │
│  (React+JS) │     │   REST API    │     │   Counters  │     │   + Sessions│
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────┘
```

See [DESIGN.md](DESIGN.md) for full architecture documentation.  
See [CHOICES.md](CHOICES.md) for engineering trade-off rationale.

## Project Structure

```
store-intelligence/
├── docker-compose.yml          # Orchestrates all services
├── .env.example                # Environment variables template
├── README.md                   # This file
├── DESIGN.md                   # System design document
├── CHOICES.md                  # Engineering decisions rationale
│
├── data/                       # Video files and CSV data (gitignored)
│
├── services/
│   ├── ingestion/              # Computer vision pipeline
│   ├── consumer/               # Event processing & session management
│   ├── api/                    # REST API + WebSocket server
│   └── dashboard/              # Static HTML dashboard
│
├── infra/
│   ├── postgres/init.sql       # Database schema
│   ├── redis/redis.conf        # Redis configuration
│   └── prometheus/             # Prometheus scraping config
│
└── tests/
    ├── unit/                   # Unit tests for core logic
    └── integration/            # API integration tests
```

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env`:

```bash
# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=purplle_store
POSTGRES_USER=purplle
POSTGRES_PASSWORD=purplle_secret

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Store config
STORE_ID=ST1008
STORE_NAME=Brigade_Bangalore

# Detection
SIMULATION_MODE=true          # Auto-detected if no video present
YOLO_MODEL=yolov8n.pt
TRIPWIRE_Y_RATIO=0.15

# Logging
LOG_LEVEL=INFO
```

## Simulation Mode

When no video file is present in `data/videos/`, the system automatically runs in **Simulation Mode**:

- Generates ~96 unique visitors based on ground truth transaction data
- Simulates 24 purchases matching the CSV records
- Creates realistic zone browsing patterns (makeup dominant at 64%)
- Includes 5 staff members filtered from footfall counts
- Produces consistent metrics across all endpoints

This ensures the system works for evaluation without requiring actual CCTV footage.

## Metrics Calibration

The system is calibrated against known ground truth:

- **24 transactions** from April 10, 2026 CSV
- **₹44,920 GMV** / **₹34,831 NMV** total revenue
- **~96 unique visitors** (derived from 24 purchases / 25% conversion rate)
- **5 staff members** excluded from footfall

All endpoints return mathematically consistent values:
- `/metrics` conversion_rate = `/funnel` purchased ÷ entered
- Funnel stages are strictly non-increasing
- Re-entries don't inflate unique visitor counts

## Testing

Run unit tests:
```bash
docker compose exec api pytest tests/unit/
```

Run integration tests (requires running stack):
```bash
docker compose exec api pytest tests/integration/
```

## Troubleshooting

**Services won't start:**
```bash
docker compose logs
docker compose down -v
docker compose up --build
```

**API not responding:**
```bash
curl http://localhost:8000/health
docker compose logs api
```

**Dashboard blank:**
- Check browser console for WebSocket errors
- Verify API is running: `curl http://localhost:8000/metrics`

## License

Proprietary — Purplle Tech Challenge 2026
