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
- [Features](FEATURES.md) - Complete feature list and requirements
- [Rust Implementation Guide](RUST_GUIDE.md) - Development and deployment guide

## Technology Stack

- **Backend:**
  - Rust with Axum web framework
  - PostgreSQL database
  - Full-text search
  - REST API with pagination

## Key Features

### Conference Management
- Track conference details (dates, locations, URLs)
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
   # Development mode
   cargo watch -x run
   
   # Production mode
   cargo run --release
   ```

## API Documentation

The API provides the following main endpoints:

```
/api/v1/conferences    # Conference management
/api/v1/publications   # Publication tracking
/api/v1/authors       # Author profiles
/api/v1/committees    # Committee management
```

Each endpoint supports:
- Pagination
- Full-text search
- Filtering
- Sorting

For detailed API documentation, run the server and visit `/api/docs`.

## API Implementation

See [RUST_GUIDE.md](RUST_GUIDE.md) for detailed API implementation with pagination and search functionality.

## Deployment

See [POSTGRES_GUIDE.md](POSTGRES_GUIDE.md) for deployment configuration on Jelastic Cloud.

## Development Workflow

1. **Local Development**
   ```bash
   # Install Rust
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   
   # Install PostgreSQL
   brew install postgresql@15
   
   # Setup local database
   createdb quantumdb
   ```

## Development

See [RUST_GUIDE.md](RUST_GUIDE.md) for detailed development instructions, including:
- Project setup
- Database migrations
- Testing
- Deployment

## Database Schema

See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for the complete database structure, including:
- Table definitions
- Relationships
- Indexes
- Materialized views

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details
