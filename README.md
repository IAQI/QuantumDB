# QuantumDB

A REST API service for tracking quantum computing conferences (QIP, QCrypt, TQC), built with Rust and PostgreSQL.

## Overview

QuantumDB provides a comprehensive system for tracking:
- Conference events and their details
- Publications and presentations
- Author profiles and contributions
- Committee memberships and roles
- Video recordings and presentation materials

## Documentation

- [Architecture](ARCHITECTURE.md) - System design and technical stack
- [Database Schema](DATABASE_SCHEMA.md) - Detailed database structure
- [Testing](TESTING.md) - Test suite and development testing guide
- [Data Population](DATA_POPULATION.md) - CSV-based scrape/import data pipeline
- [Data Ingestion Plan](docs/DATA_INGESTION_PLAN.md) - Per-conference data inventory and working plan
- [CLAUDE.md](CLAUDE.md) - Detailed development guide (commands, workflow, conventions)

## Technology Stack

- **Backend:**
  - Rust with Axum web framework
  - PostgreSQL database with full-text search capabilities
  - SQLx for type-safe database queries
  - OpenAPI/Swagger UI for interactive API documentation
  - Unicode normalization for author name processing
  - REST API with CRUD operations for all entities

## Key Features

### Conference Management
- Track conference details (dates, locations, URLs)
- Archive URLs for static website backups
- Monitor submission and acceptance statistics
- Store proceedings and website links

### Publication Tracking
- Full paper metadata
- Author affiliations
- Presentation materials
- Video recordings
- DOI integration

### Author Profiles
- Publication history
- Committee service records
- ORCID integration
- Affiliation tracking

### Committee Management
- Program Committee tracking
- Steering Committee records
- Local organizer information
- Historical service records

## Getting Started

### Using Docker (Recommended)

1. **Clone and Configure**
   ```bash
   git clone https://github.com/yourusername/QuantumDB.git
   cd QuantumDB
   
   # Generate API token
   ./tools/generate_token.sh
   
   # Add token to .env file (or set as environment variable)
   echo "API_TOKENS=your-generated-token" >> .env
   ```

2. **Start Services**
   ```bash
   # Build and start (PostgreSQL + QuantumDB + PgAdmin)
   docker compose up -d --build
   
   # Check logs
   docker compose logs -f app
   ```

3. **Access the Application**
   - Web Interface: http://localhost:3000
   - Swagger UI: http://localhost:3000/api/v1/swagger-ui/
   - PgAdmin: http://localhost:5050 (admin@example.com / quantumdb)

### Local Development

1. **Prerequisites**
   ```bash
   # Install Rust
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   
   # Install PostgreSQL
   brew install postgresql@15
   
   # Install development tools
   cargo install sqlx-cli cargo-watch cargo-audit
   ```

2. **Environment Configuration**
   ```bash
   # Create .env file
   cat > .env << EOF
   DATABASE_URL=postgres://quantumdb:quantumdb@localhost:5432/quantumdb
   API_TOKENS=$(./tools/generate_token.sh)
   EOF
   ```

3. **Database Setup**
   ```bash
   # Start PostgreSQL
   brew services start postgresql@15
   
   # Create database
   createdb quantumdb
   
   # Run migrations
   sqlx migrate run
   ```

4. **Run the Application**
   ```bash
   # Development mode with auto-reload
   cargo watch -x run
   
   # Production mode
   cargo run --release
   ```

5. **Access Services**
   - Web Interface: http://localhost:3000
   - Swagger UI: http://localhost:3000/api/v1/swagger-ui/

## Features

### Web Interface

QuantumDB provides a user-friendly web interface for browsing and exploring quantum computing conference data:

- **Homepage** - Overview and quick access to key resources
- **About Page** - Project information and IAQI branding
- **Author Directory** - Browse and search researchers in quantum computing
- **Conference Browser** - Explore conferences by venue (QIP, QCrypt, TQC)
- **Dynamic Loading** - HTMX-powered for smooth, fast navigation

### REST API

**Interactive API Explorer**: Visit `/api/v1/swagger-ui/` when running the server for complete interactive API documentation with live testing capabilities.

All API endpoints are fully documented with request/response schemas, examples, and try-it-now functionality. The REST API is versioned under `/api/v1/`.

**Hardening**: every response carries security headers (`X-Frame-Options`, `X-Content-Type-Options`, etc.), requests are rate-limited per IP, and CORS is applied. See [CLAUDE.md](CLAUDE.md) for the middleware stack details.

### Authentication

Write operations (POST, PUT, DELETE) and admin endpoints require Bearer token authentication. All read operations (GET) remain publicly accessible.

**Generating API Tokens:**
```bash
# Generate a secure token using the included script
./tools/generate_token.sh

# Or manually with openssl
openssl rand -base64 32 | tr -d '=/' | tr '+' '-'
```

**Using Authentication:**
```bash
# Include the token in the Authorization header
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"venue": "QIP", "year": 2026, "creator": "you", "modifier": "you"}' \
  http://localhost:3000/api/v1/conferences
```

**Setting Up Tokens:**

1. **Generate a Token:**
   ```bash
   ./tools/generate_token.sh
   ```

2. **Configure for Docker:**
   Add to your `.env` file (gitignored):
   ```bash
   API_TOKENS=your-secure-token-here
   ```
   
   Docker Compose will automatically load environment variables from `.env`.

3. **Configure for Local Development:**
   Set as environment variable:
   ```bash
   export API_TOKENS=your-secure-token-here
   cargo run
   ```

4. **Multiple Users:**
   Support multiple tokens (comma-separated):
   ```bash
   API_TOKENS=token1,token2,token3
   ```

**Protected Endpoints:**
- All POST, PUT, DELETE operations on `/api/v1/conferences`, `/api/v1/authors`, `/api/v1/publications`, `/api/v1/committees`, `/api/v1/authorships`
- `GET /admin/refresh-stats` (admin materialized view refresh)

**Public Endpoints:**
- All GET operations (read-only access)
- Web interface routes
- `/health` endpoint
- Swagger UI documentation

**Token Requirements:**
- Minimum 32 characters
- The token body is opaque — any character set is accepted
- Use cryptographically secure random generation
- Comparison is constant-time (`subtle` crate) against every configured token
- Store securely and never commit to version control

### API Endpoints

The API provides full CRUD operations (all under the versioned `/api/v1/` prefix) for:

```
/api/v1/conferences   # Conference management
/api/v1/publications  # Publication tracking
/api/v1/authors       # Author profiles
/api/v1/authorships   # Author-publication relationships
/api/v1/committees    # Committee role management
```

All endpoints are documented with:
- Request/response schemas
- Example payloads
- Live testing interface
- OpenAPI 3.0 specification at `/api/v1/openapi.json`

## Development

See [TESTING.md](TESTING.md) for testing instructions and [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for the complete database structure.

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details
