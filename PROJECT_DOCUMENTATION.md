# RealtimeKit-Learning: Farmer-Veterinarian Video Consultation Platform

## Project Overview

**RealtimeKit-Learning** is a full-stack web application that enables real-time video consultations between farmers and veterinarians. The platform uses **Dyte SDK** (Cloudflare Realtime API) to facilitate peer-to-peer video meetings with minimal latency and high reliability.

### Purpose
The application solves the problem of accessible veterinary consultations for farmers by providing:
- **Easy meeting creation** via a simple dashboard
- **Separate roles** for farmers and veterinarians with preset configurations
- **Real-time video/audio** communication with Dyte's optimized infrastructure
- **Share-friendly links** for participants to join without additional setup

---

## Tech Stack

### Frontend
- **Framework**: Next.js 16.2.9
- **Language**: TypeScript
- **UI Library**: React 19.2.4
- **Video SDK**: @dytesdk/react-ui-kit (3.0.8), @dytesdk/react-web-core (3.1.11)
- **Styling**: Tailwind CSS 4
- **Build Tool**: Next.js App Router
- **Linting**: ESLint 9

### Backend
- **Framework**: Django 6.0.6
- **Language**: Python
- **API**: Django REST Framework
- **API Gateway**: Dyte's Cloudflare Realtime API (v2)
- **Database**: SQLite (development)
- **Environment**: Python virtual environment

### External Services
- **Video Provider**: Dyte (Cloudflare Realtime)
  - Base URL: `https://api.realtime.cloudflare.com/v2`
  - Authentication: API key + Auth headers
  - Required env vars: `DYTE_BASE_URL`, `DYTE_ORG_ID`, `DYTE_API_KEY`, `DYTE_AUTH_HEADER`

---

## Project Structure

```
d:\RealtimeKit-Learning/
├── backend/                      # Django REST API
│   ├── manage.py                # Django management tool
│   ├── db.sqlite3               # Development database
│   ├── api/                     # Main API app
│   │   ├── models.py            # (Currently empty - ready for expansion)
│   │   ├── views.py             # API endpoints (health check, create meeting)
│   │   ├── urls.py              # URL routing
│   │   ├── admin.py             # Django admin config
│   │   ├── apps.py              # App configuration
│   │   ├── migrations/          # Database migrations
│   │   └── tests.py             # Tests
│   └── config/                  # Django project settings
│       ├── settings.py          # Django configuration (CORS, Dyte creds)
│       ├── urls.py              # Main URL router
│       ├── asgi.py              # ASGI config (async support)
│       └── wsgi.py              # WSGI config (standard deployment)
│
└── frontend/                     # Next.js React application
    ├── package.json             # NPM dependencies
    ├── tsconfig.json            # TypeScript configuration
    ├── next.config.ts           # Next.js configuration
    ├── postcss.config.mjs        # PostCSS setup (Tailwind)
    ├── eslint.config.mjs        # ESLint rules
    ├── tailwind.config.js       # Tailwind CSS config
    ├── app/                     # Next.js App Router
    │   ├── layout.tsx           # Root layout wrapper
    │   ├── page.tsx             # Home page (meeting creation)
    │   ├── globals.css          # Global styles
    │   ├── farmer/
    │   │   └── page.tsx         # Farmer meeting view
    │   └── vet/
    │       └── page.tsx         # Veterinarian meeting view
    ├── lib/
    │   └── api.ts               # API client utility
    ├── components/              # Reusable React components
    ├── public/                  # Static assets
    └── README.md                # Next.js default README

```

---

## Completed Features

### 1. **Backend API (Django)**

#### Endpoints Implemented:

##### Health Check
- **Endpoint**: `GET /api/health/`
- **Purpose**: Verify backend is running
- **Response**: `{ "status": "ok", "message": "Backend is working successfully!" }`

##### Create Meeting
- **Endpoint**: `POST /api/create-meeting/`
- **Purpose**: Create a new consultation meeting with farmer and vet participants
- **Flow**:
  1. **Create Meeting** via Dyte API
     - Title: "Vet Consultation"
     - Returns: Meeting ID
  
  2. **Create Farmer Participant**
     - Role: Group call participant
     - Preset: `group_call_participant`
     - Auto-generated unique ID
     - Returns: Farmer auth token + join URL
  
  3. **Create Veterinarian Participant**
     - Role: Group call host (can control meeting settings)
     - Preset: `group_call_host`
     - Auto-generated unique ID
     - Returns: Vet auth token + join URL

- **Response Structure**:
  ```json
  {
    "meeting": {
      "id": "meeting_uuid",
      ...
    },
    "farmer": {
      "join_url": "https://meet.dyte.in/...",
      "auth_token": "..."
    },
    "vet": {
      "join_url": "https://meet.dyte.in/...",
      "auth_token": "..."
    }
  }
  ```

#### Configuration:
- **CORS enabled** for frontend at `http://localhost:3000`
- **Environment variables** required in `.env`:
  - `DYTE_BASE_URL`: Dyte API base URL
  - `DYTE_ORG_ID`: Organization ID from Dyte
  - `DYTE_API_KEY`: API key for authentication
  - `DYTE_AUTH_HEADER`: Pre-formatted Authorization header

---

### 2. **Frontend Application (Next.js/React)**

#### Pages Implemented:

##### Home Page (`/`)
- **File**: [app/page.tsx](app/page.tsx)
- **Functionality**:
  - "Create Meeting" button that calls backend API
  - Displays meeting creation results including:
    - Meeting ID
    - Farmer join link (with copy button and direct open button)
    - Veterinarian join link (with copy button and direct open button)
  - User-friendly UI with buttons for quick actions
  - Error handling with alerts

##### Farmer Page (`/farmer?token=<auth_token>`)
- **File**: [app/farmer/page.tsx](app/farmer/page.tsx)
- **Functionality**:
  - Receives auth token from URL query parameter
  - Initializes Dyte meeting client with:
    - Default audio enabled
    - Default video enabled
  - Displays loading state ("Joining Farmer...")
  - Renders Dyte UI Kit meeting component
  - Full-screen meeting interface

##### Veterinarian Page (`/vet?token=<auth_token>`)
- **File**: [app/vet/page.tsx](app/vet/page.tsx)
- **Functionality**:
  - Receives auth token from URL query parameter
  - Initializes Dyte meeting client with:
    - Default audio enabled
    - Default video enabled
  - Displays loading state ("Joining Vet Consultation...")
  - Renders Dyte UI Kit meeting component
  - Full-screen meeting interface

#### API Client
- **File**: [lib/api.ts](lib/api.ts)
- **Function**: `createMeeting()`
  - Makes POST request to `http://127.0.0.1:8000/api/create-meeting/`
  - Handles response parsing
  - Includes error handling

#### Styling
- **Tailwind CSS** configured and integrated
- **Global styles** in [app/globals.css](app/globals.css)
- **Responsive design** ready for implementation

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     FARMER OR VET BROWSER                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Home Page (/):                                               │
│  1. User clicks "Create Meeting"                              │
│  2. Calls: POST /api/create-meeting/                          │
│                          │                                    │
│                          ▼                                    │
└──────────────────── FRONTEND API CLIENT ─────────────────────┘
                              │
                              ▼ (HTTP Request)
┌──────────────────── BACKEND DJANGO API ────────────────────┐
│                                                              │
│  API View: create_meeting()                                 │
│  1. Create meeting via Dyte API                             │
│  2. Create farmer participant                               │
│  3. Create vet participant                                  │
│  4. Return meeting + tokens + join URLs                     │
│                                                              │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼ (HTTP Response)
        ┌─────────────────────────────────┐
        │  JSON with join URLs and tokens │
        └─────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
         ┌─────────────────────┐ ┌──────────────────┐
         │  Display Farmer Link │ │ Display Vet Link │
         │  /farmer?token=xxx  │ │ /vet?token=xxx   │
         └─────────────────────┘ └──────────────────┘
                    │                   │
          (Share or click link)
                    │                   │
         ┌──────────▼────────────────────▼──────────┐
         │  Meeting Join Pages Load Token            │
         │  Initialize Dyte Client                  │
         │  Render Full-Screen Meeting Interface    │
         └──────────────────────────────────────────┘
                              │
                              ▼
         ┌───────────────────────────────────────┐
         │  Real-Time Video Conference via Dyte  │
         │  (Cloudflare Realtime API)             │
         └───────────────────────────────────────┘
```

---

## Environment Setup & Running Instructions

### Prerequisites
- Node.js 18+ (for frontend)
- Python 3.10+ (for backend)
- npm or yarn (frontend package manager)

### Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install django djangorestframework django-cors-headers python-decouple requests

# Create .env file with:
DYTE_BASE_URL=https://api.realtime.cloudflare.com/v2
DYTE_ORG_ID=your_org_id_here
DYTE_API_KEY=your_api_key_here
DYTE_AUTH_HEADER=Authorization: Basic <base64_encoded_credentials>

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
# Server runs at http://127.0.0.1:8000/
```

### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Create .env.local (if needed for API endpoints)
# API URL is hardcoded in lib/api.ts as http://127.0.0.1:8000/api

# Start development server
npm run dev
# Server runs at http://localhost:3000/
```

---

## Testing the Application

### Step 1: Create a Meeting
1. Open http://localhost:3000/
2. Click "Create Meeting" button
3. Observe the response showing meeting details

### Step 2: Join as Farmer
1. Copy the Farmer join link OR click "Join as Farmer"
2. Browser redirects to `/farmer?token=<auth_token>`
3. Loading state shows "Joining Farmer..."
4. Once loaded, Dyte UI appears with video/audio controls

### Step 3: Join as Veterinarian
1. Copy the Vet join link OR click "Join as Veterinarian"
2. Browser redirects to `/vet?token=<auth_token>`
3. Loading state shows "Joining Vet Consultation..."
4. Once loaded, Dyte UI appears with video/audio controls

### Step 4: Video Consultation
- Both participants can see and hear each other in real-time
- Dyte UI Kit provides:
  - Video/audio mute controls
  - Screen sharing capabilities
  - Chat functionality
  - Participant list
  - Meeting controls

---

## API Integration with Dyte (Cloudflare Realtime)

### Authentication Flow
1. **Backend holds credentials** (never exposed to frontend)
2. **Backend creates participants** in Dyte meeting
3. **Backend generates auth tokens** for each participant
4. **Frontend receives tokens** via response
5. **Frontend initializes** Dyte client with tokens
6. **Frontend connects directly** to Dyte's meeting infrastructure

### Dyte API Calls Made
```
POST https://api.realtime.cloudflare.com/v2/meetings
├── Creates new meeting room
└── Returns: meeting ID

POST https://api.realtime.cloudflare.com/v2/meetings/{meeting_id}/participants
├── Creates farmer participant
├── Creates vet participant
└── Returns: auth tokens + join URLs
```

---

## Current Limitations & Future Enhancements

### Current Limitations
- ✅ Models not yet utilized (currently using Dyte's meeting structure directly)
- ✅ No database persistence of meetings
- ✅ No user authentication system
- ✅ No meeting history/records
- ✅ Basic UI without advanced styling
- ✅ No admin interface for managing meetings
- ✅ No error recovery or retry logic

### Recommended Future Enhancements
1. **Database Integration**
   - Store meetings in Django models
   - Track participants and meeting history
   - Add timestamps and duration logging

2. **User Authentication**
   - JWT-based auth for secure access
   - Role-based permissions (farmer/vet)
   - User profiles

3. **Enhanced UI**
   - Tailwind styling for professional look
   - Mobile responsiveness
   - Real-time meeting status updates
   - Meeting recordings (if Dyte supports)

4. **Advanced Features**
   - Meeting scheduling
   - Participant invitations via email
   - Meeting notes/prescriptions
   - Payment integration
   - Admin dashboard

5. **Backend Enhancements**
   - Logging and monitoring
   - Rate limiting
   - Meeting analytics
   - Webhook integration for Dyte events

---

## Dependencies

### Backend
```
Django==6.0.6
djangorestframework==3.14.x
django-cors-headers==4.x
python-decouple==3.x
requests==2.x
```

### Frontend
```
next@16.2.9
react@19.2.4
react-dom@19.2.4
@dytesdk/react-ui-kit@3.0.8
@dytesdk/react-web-core@3.1.11
@dytesdk/web-core@3.1.11
tailwindcss@4
typescript@5
eslint@9
```

---

## Deployment Considerations

### Backend (Django)
- Use Gunicorn/uWSGI for production
- Set `DEBUG = False` in settings
- Use environment variables for secrets
- Set proper `ALLOWED_HOSTS`
- Enable HTTPS (required by Dyte)
- Use managed database (PostgreSQL recommended)

### Frontend (Next.js)
- Use `npm run build && npm run start` for production
- Deploy to Vercel (native Next.js support)
- Or use Docker for custom deployment
- Set API_URL to production backend

### Environment
- Use environment variables for all secrets
- Never commit `.env` files
- Use `.env.example` as template

---

## Troubleshooting

### "Failed to create consultation"
- Check backend is running (`python manage.py runserver`)
- Verify DYTE credentials in `.env`
- Check browser console for exact error

### "Invalid farmer/vet link"
- Ensure token is passed in URL: `/farmer?token=...`
- Check token wasn't corrupted during copy/paste

### "Unable to join meeting"
- Check Dyte credentials
- Verify firewall allows HTTPS to Dyte API
- Check browser console for detailed error

### CORS errors
- Verify frontend URL in `CORS_ALLOWED_ORIGINS` (settings.py)
- Check `Content-Type: application/json` header in requests

---

## Contact & Support

For issues with:
- **Dyte SDK**: https://dyte.io/docs/
- **Next.js**: https://nextjs.org/docs/
- **Django**: https://docs.djangoproject.com/

---

**Project Created**: 2025
**Last Updated**: 2026-07-06
**Status**: Active Development
