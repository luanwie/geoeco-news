# Overview

NewsAlert is a SaaS platform that monitors economic, geopolitical, and market news in real-time and delivers filtered alerts directly to users via WhatsApp. The MVP provides automated news scraping, intelligent filtering based on keywords and relevance scoring, and formatted WhatsApp notifications for high-impact news events.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture
- **Framework**: FastAPI with Python for REST API and web interface
- **Database**: SQLite for local data storage with SQLAlchemy ORM
- **Background Processing**: APScheduler for automated news scraping every 15 minutes
- **Authentication**: JWT tokens with passlib for password hashing
- **Template Engine**: Jinja2 for server-side rendered HTML pages

## Frontend Architecture
- **Approach**: Server-side rendered templates with Bootstrap 5 for responsive UI
- **Static Assets**: Served via FastAPI's StaticFiles mounting
- **Styling**: Bootstrap CSS framework with Font Awesome icons
- **JavaScript**: Vanilla JS (minimal client-side logic)

## News Processing Pipeline
- **Scraping Strategy**: Multi-source web scraping from Reuters Brasil, G1 Economia, and InfoMoney
- **Content Filtering**: Keyword-based categorization for economy, geopolitics, and markets
- **Relevance Scoring**: Articles mentioned across multiple sources trigger "high impact" alerts
- **Processing Schedule**: Automated pipeline runs every 15 minutes via background scheduler

## Data Models
- **Users**: Authentication, subscription plans (free/pro/pro_annual), trial periods, Stripe integration
- **Alerts**: Historical record of sent notifications with content and metadata
- **UserCategory**: User preferences for news categories (economy, geopolitics, markets)
- **NewsItem**: Scraped articles with content, URLs, and timestamps

## Authentication & Authorization
- **Session Management**: JWT-based authentication with secure cookie storage
- **Password Security**: Bcrypt hashing via passlib
- **Access Control**: Route-level protection for dashboard and settings pages
- **Trial System**: 2-day free trial with automatic expiration tracking

## Subscription Management
- **Payment Processing**: Stripe integration for Pro plans (R$49.99/month, R$499.90/annual)
- **Plan Enforcement**: Trial expiration and plan-based feature access control
- **Customer Management**: Stripe customer ID storage for subscription tracking

# External Dependencies

## Payment Processing
- **Stripe**: Subscription billing and payment processing
- **Integration**: Customer creation, subscription management, webhook handling

## Communication Services
- **WaSenderAPI**: WhatsApp message delivery service
- **Message Format**: Structured alerts with emojis, categories, and timestamps
- **Phone Validation**: Brazilian phone number format validation (55XXXXXXXXXXX)

## Web Scraping
- **BeautifulSoup**: HTML parsing and content extraction
- **Requests**: HTTP client for fetching news articles
- **Target Sources**: Reuters Brasil, G1 Economia, InfoMoney

## Infrastructure
- **Deployment**: Replit hosting environment
- **Environment Variables**: API keys and configuration via environment variables
- **Static Files**: CSS, JavaScript, and image assets served locally

## Third-Party Libraries
- **FastAPI**: Web framework and API development
- **SQLAlchemy**: Database ORM and connection management
- **APScheduler**: Background job scheduling
- **Passlib**: Password hashing and verification
- **PyJWT**: JWT token generation and validation
- **Bootstrap**: Frontend CSS framework
- **Font Awesome**: Icon library for UI enhancement