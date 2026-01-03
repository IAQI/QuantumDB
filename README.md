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

1. **Prerequisites**
   ```bash
   # Install Rust
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   
   # Install PostgreSQL
   brew install postgresql@15
   
   # Install development tools
   cargo install sqlx-cli cargo-watch cargo-audit
   ```

2. **Database Setup**
   ```bash
   # Start PostgreSQL
   brew services start postgresql@15
   
   # Create database
   createdb quantumdb
   
   # Run migrations
   sqlx migrate run
   ```

3. **Run the Application**
   ```bash
   # Development mode with auto-reload
   cargo watch -x run
   
   # Production mode
   cargo run --release
   
   # Access Swagger UI
   # http://localhost:3000/swagger-ui/
   ```

## API Documentation

**Interactive API Explorer**: Visit `/swagger-ui/` when running the server for complete interactive API documentation with live testing capabilities.

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
  -d '{"name": "QIP", "year": 2026}' \
  http://localhost:3000/api/conferences
```

**Setting Up Tokens:**

For Docker deployment, add to your environment:
```bash
# Single token
export API_TOKENS=your-secure-token-here

# Multiple tokens (comma-separated for multiple users)
export API_TOKENS=token1,token2,token3
```

Or update `docker-compose.yml`:
```yaml
environment:
  - API_TOKENS=your-secure-token-here
```

**Protected Endpoints:**
- All POST, PUT, DELETE operations on `/api/conferences`, `/api/authors`, `/api/publications`, `/api/committees`, `/api/authorships`
- `GET /admin/refresh-stats` (admin materialized view refresh)

**Public Endpoints:**
- All GET operations (read-only access)
- Web interface routes
- `/health` endpoint
- Swagger UI documentation

**Token Requirements:**
- Minimum 32 characters
- Alphanumeric characters plus hyphens (-) and underscores (_)
- Use cryptographically secure random generation
- Store securely and never commit to version control

### API Endpoints

The API provides full CRUD operations for:

```
/conferences          # Conference management
/publications         # Publication tracking
/authors             # Author profiles
/authorships         # Author-publication relationships
/committees          # Committee role management
```

All endpoints are documented with:
- Request/response schemas
- Example payloads
- Live testing interface
- OpenAPI 3.0 specification at `/api-docs/openapi.json`

## Development

See [TESTING.md](TESTING.md) for testing instructions and [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for the complete database structure.

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details
