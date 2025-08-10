# DriveLink

## Overview

DriveLink is an "Uber for Driving Instructors" marketplace platform that connects students with verified driving instructors through a subscription-based model. The platform combines WhatsApp integration for seamless communication with a comprehensive web portal for instructors to manage their driving instruction business. Instructors pay monthly subscription fees to access the platform and earn commission-based revenue from lessons.

## System Architecture

### Frontend Architecture
- **Web Framework**: Flask with Jinja2 templating
- **UI Framework**: Bootstrap (Replit dark theme) with Feather icons
- **Client-side**: Vanilla JavaScript for enhanced interactions
- **Responsive Design**: Mobile-first approach using Bootstrap grid system

### Backend Architecture
- **Web Framework**: Flask (Python 3.11)
- **Database ORM**: SQLAlchemy with Flask-SQLAlchemy extension
- **Authentication**: Replit Auth with OAuth2 integration via Flask-Dance
- **Session Management**: Flask-Login for user session handling
- **WSGI Server**: Gunicorn for production deployment

### Database Design
- **ORM**: SQLAlchemy with declarative base
- **User Management**: Role-based access control (instructor, admin, super_admin)
- **Data Models**: Users, OAuth tokens, Students, Lessons, WhatsApp sessions
- **Database Features**: Connection pooling, automatic reconnection, table auto-creation

## Key Components

### Authentication System
- **Replit OAuth Integration**: Secure authentication via Replit's OAuth provider
- **Role-based Access Control**: Three-tier permission system
- **Session Storage**: Custom UserSessionStorage for OAuth token management
- **User Loader**: Flask-Login integration for session persistence

### User Role System
- **Instructors**: Manage assigned students and lessons
- **Admins**: Full driving school operations management
- **Super Admins**: System-wide configuration and user management

### WhatsApp Integration
- **Dual User Support**: Same bot handles both students and instructors based on phone number recognition
- **Student Features**: Lesson booking, progress tracking, instructor finding, balance management
- **Instructor Features**: Student management, lesson scheduling, progress monitoring, lesson status updates
- **Session Management**: Context-aware conversation tracking for complex workflows
- **Real-time Notifications**: Automatic lesson confirmations, cancellations, and reminders

### Web Portal Features
- **Dashboard System**: Role-specific dashboards with relevant statistics
- **Student Management**: Registration, assignment, and progress tracking
- **Lesson Scheduling**: Booking system with status tracking
- **Responsive UI**: Mobile-friendly interface with dark theme

## Data Flow

### Student Registration Flow
1. Admin registers student via web portal
2. Student WhatsApp number is verified and stored
3. Student is assigned to an instructor
4. Student can interact via WhatsApp bot

### Lesson Booking Flow
1. Student initiates booking via WhatsApp
2. System checks availability and instructor assignment
3. Lesson is scheduled with appropriate status
4. Notifications sent to relevant parties

### Authentication Flow
1. User accesses web portal
2. Redirected to Replit OAuth provider
3. OAuth token stored in database
4. User session established with role-based permissions

## External Dependencies

### Core Dependencies
- **Flask**: Web framework and extensions (SQLAlchemy, Login)
- **Gunicorn**: WSGI HTTP server for production
- **Werkzeug**: WSGI utilities and security features
- **SQLAlchemy**: Database ORM and connection management
- **Psycopg2**: PostgreSQL adapter

### Authentication Dependencies
- **Flask-Dance**: OAuth integration library
- **PyJWT**: JSON Web Token handling
- **OAuthLib**: OAuth protocol implementation

### UI Dependencies
- **Bootstrap**: CSS framework (via CDN)
- **Feather Icons**: Icon library (via CDN)
- **Custom CSS/JS**: Application-specific styling and behavior

### Development Dependencies
- **Email Validator**: Email address validation
- **Python 3.11**: Runtime environment

## Deployment Strategy

### Replit Configuration
- **Runtime**: Python 3.11 with Nix package management
- **Services**: PostgreSQL and OpenSSL packages
- **Deployment**: Autoscale target with Gunicorn binding
- **Development**: Hot reload with port forwarding

### Production Setup
- **WSGI Server**: Gunicorn with multiple workers
- **Database**: PostgreSQL with connection pooling
- **Security**: ProxyFix middleware for HTTPS handling
- **Environment**: Configuration via environment variables

### Database Management
- **Auto-creation**: Tables created on application startup
- **Connection Health**: Pre-ping and connection recycling
- **Session Management**: Proper cleanup and error handling

## Configuration

### Environment Variables (.env file)
The application now uses a .env file for easy configuration management:

- **TWILIO_ACCOUNT_SID**: Your Twilio Account SID
- **TWILIO_AUTH_TOKEN**: Your Twilio Auth Token  
- **TWILIO_PHONE_NUMBER**: Your Twilio WhatsApp phone number (e.g., whatsapp:+14155238886)
- **TWILIO_TEMPLATE_SID**: Twilio template ID for Quick Reply buttons (HXf324aa725113107f86055b1cc3d4092a)
- **SESSION_SECRET**: Flask session secret key

### WhatsApp Bot Features
- **Dual Interface**: Automatically detects students vs instructors by phone number
- **Student Commands**: book, lessons, progress, cancel, help, menu, instructors, balance, fund
- **Instructor Commands**: students, today, schedule, lessons, cancel [id], confirm [id], complete [id], availability, help
- **Simple numbered options**: Clean, reliable text-based interaction system
- **Session state management** for booking flow tracking
- **Interactive lesson booking** with duration selection (30/60 minutes)
- **Progress tracking** and lesson management with numbered navigation
- **Real-time Twilio integration** for live WhatsApp messaging
- **Comprehensive booking system** with availability checking

### Current Implementation (July 16, 2025)
- **Numbered Options**: Simple 1, 2, 3 format for all interactions
- **Clean Format**: No special characters or emojis, just clear numbered lists
- **Reliable**: Works with all Twilio accounts without special approvals
- **User-Friendly**: Easy to use by simply typing numbers
- **Session Flow**: Maintains conversation context for multi-step bookings

## Changelog

- August 10, 2025: **MAJOR TRANSFORMATION**: Complete platform overhaul into "Uber for Driving Instructors" marketplace model:
  - Implemented subscription-based revenue model with three tiers (Basic $29/month, Premium $49/month, Pro $99/month)
  - Added comprehensive instructor onboarding system with license verification and profile setup
  - Created student marketplace for finding and booking instructors by location and ratings
  - Integrated Stripe payment processing for subscription billing and commission handling
  - Built commission-based earnings system with real-time analytics and reporting
  - Added subscription management dashboard for instructors with earnings tracking
  - Created public marketplace interface for students to discover instructors
  - Transformed landing page to showcase marketplace benefits and subscription plans
- August 1, 2025: Complete rebranding to DriveLink - updated all templates, JavaScript files, email addresses, and documentation to use consistent DriveLink branding throughout the system
- July 31, 2025: Added instructor WhatsApp functionality - instructors can now use the same WhatsApp bot with dedicated features like viewing students, managing lessons, and checking schedules
- July 31, 2025: Successfully migrated from Replit Agent to Replit environment with PostgreSQL database setup, fixed JavaScript errors, and restored DriveLink branding
- July 16, 2025: Simplified to reliable numbered text system (1, 2, 3) instead of Quick Reply buttons due to WhatsApp Business approval requirements
- July 9, 2025: Added .env configuration support and Twilio template integration
- June 25, 2025: Initial setup

## User Preferences

- **Communication style**: Simple, everyday language
- **WhatsApp interaction**: Clean numbered options (1, 2, 3) instead of buttons or emojis
- **Reliability over complexity**: Prefer solutions that work immediately without special approvals