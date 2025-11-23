# Admin Dashboard - Shoe Type Identification System

## Overview

The Admin Dashboard is a Next.js application for managing users, monitoring crawlers, viewing statistics, and configuring system settings for the Shoe Type Identification System.

## Quick Start

```powershell
# Install dependencies
npm install

# Set up environment variables
cp .env.local.example .env.local
# Edit .env.local with your backend API URL

# Run development server
npm run dev

# Build for production
npm run build
npm start
```

**Access:** http://localhost:3001

**Default Admin Login:**
- Email: `admin@shoeidentifier.local`
- Password: `admin123`

## Project Structure

```
admin/
├── app/
│   ├── page.jsx                    # Dashboard home with statistics
│   ├── layout.jsx                  # Root layout with navigation
│   ├── globals.css                 # Global styles
│   ├── login/
│   │   └── page.jsx               # Admin login (with MFA support)
│   ├── users/
│   │   └── page.jsx               # User management & moderation
│   ├── crawlers/
│   │   └── page.jsx               # Crawler control & scheduling
│   ├── statistics/
│   │   └── page.jsx               # Analytics & performance metrics
│   └── settings/
│       └── page.jsx               # Admin settings & configuration
├── components/
│   ├── AdminProvider.jsx          # Auth initialization wrapper
│   ├── AdminHeader.jsx            # Navigation header
│   ├── CrawlerScheduler.jsx       # Calendar-based scheduler modal
│   └── ui/                        # Reusable UI components
├── lib/
│   ├── api.js                     # API client with JWT interceptors
│   ├── store.js                   # Zustand admin store
│   └── design-system.js           # Design tokens and utilities
├── public/                         # Static assets (logos, favicons)
├── package.json                    # Dependencies
├── tailwind.config.js              # Tailwind CSS configuration
└── tsconfig.json                   # TypeScript configuration
```

## Features

### 1. Dashboard Home (`/`)
- **System Overview**: Real-time statistics cards
  - Total users count
  - Total shoes in database
  - Active crawlers count
  - System health status
- **Recent Activity**: Latest user registrations and crawler runs
- **Quick Actions**: Navigate to users, crawlers, statistics, settings

### 2. User Management (`/users`)
- **User List**: View all registered users with search/filter
- **User Details**: Email, registration date, activity level
- **Actions**:
  - View user profile
  - Suspend/unsuspend user accounts
  - Delete user accounts (with confirmation)
  - Reset user passwords
- **Bulk Actions**: Select multiple users for batch operations
- **Export**: Download user list as CSV

### 3. Crawler Control (`/crawlers`)
- **Crawler Dashboard**: Monitor 15+ web scrapers
- **Real-time Status**: Running/idle/error states with progress bars
- **Statistics per Crawler**:
  - Total items scraped
  - Unique images added
  - Uniqueness percentage
  - Last run time and next scheduled run
- **Actions**:
  - Start/stop individual crawlers
  - Schedule runs using calendar UI
  - Configure crawler settings (uniqueness threshold, schedule)
  - View crawler logs and error details
- **Calendar Scheduler**:
  - Pick date/time for crawler execution
  - "Run Now" for immediate execution
  - Automatic quarterly rescheduling (3 months)
  - Visual feedback and validation

### 4. Statistics & Analytics (`/statistics`)
- **System Metrics**: Database size, API response times, uptime
- **User Analytics**: Registration trends, active users, engagement
- **Crawler Performance**: Success rates, items per run, uniqueness trends
- **Image Processing**: Upload statistics, matching accuracy, feature quality
- **Charts & Graphs**: Interactive visualizations with Chart.js
- **Time Filters**: Last 7 days, 30 days, 90 days, all time
- **Export Reports**: Download analytics as PDF or CSV

### 5. Settings & Configuration (`/settings`)
- **Admin Profile**: Update email, name, password
- **System Settings**:
  - Image upload limits (size, formats)
  - Matching threshold configuration
  - API rate limiting
  - Session timeout
- **Email Configuration**: SMTP settings for notifications
- **Security Settings**:
  - Enable/disable MFA
  - Session duration
  - Password policy
- **Backup & Maintenance**:
  - Database backup
  - Clear cache
  - View system logs

## API Integration

The admin dashboard communicates with the Flask backend via REST API:

### Authentication
```javascript
// Login
POST /api/admin/login
Body: { email, password, mfa_token? }
Response: { token, admin_user }

// Verify MFA
POST /api/admin/verify-mfa
Body: { token, code }
```

### User Management
```javascript
// List users
GET /api/admin/users?page=1&limit=20

// Get user details
GET /api/admin/users/:id

// Update user
PUT /api/admin/users/:id
Body: { is_active, role, etc }

// Delete user
DELETE /api/admin/users/:id
```

### Crawler Management
```javascript
// List crawlers
GET /api/admin/crawlers

// Start crawler
POST /api/admin/crawlers/:id/start

// Stop crawler
POST /api/admin/crawlers/:id/stop

// Update crawler config
PUT /api/admin/crawlers/:id/config
Body: { schedule_cron, is_active, min_uniqueness_threshold }
```

### Statistics
```javascript
// System stats
GET /api/admin/stats/system

// User stats
GET /api/admin/stats/users?period=30d

// Crawler stats
GET /api/admin/stats/crawlers
```

## State Management

**Zustand Store** (`lib/store.js`):
```javascript
{
  // Auth state
  isAuthenticated: boolean,
  admin: object | null,
  token: string | null,
  
  // Actions
  login: (email, password, mfaToken?) => Promise<void>,
  logout: () => void,
  checkAuth: () => void
}
```

**LocalStorage Persistence**:
- Admin credentials persist across sessions
- Automatic token refresh
- Logout on token expiration

## Styling

**Tailwind CSS** with custom design system:
- Color palette: Blue primary, gray neutrals, status colors
- Typography: Inter font, responsive scales
- Components: Cards, buttons, inputs, modals, tables
- Responsive: Mobile-first design, breakpoints at sm/md/lg/xl
- Dark mode: Not yet implemented (planned)

## Environment Variables

Create `.env.local`:
```env
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:5000

# App Settings
NEXT_PUBLIC_APP_NAME=Shoe Type Identification System
NEXT_PUBLIC_ADMIN_PORT=3001
```

## Development

### Prerequisites
- Node.js 18+ and npm
- Backend API running on port 5000
- PostgreSQL database configured

### Commands
```bash
# Install dependencies
npm install

# Run dev server (with hot reload)
npm run dev

# Lint code
npm run lint

# Build for production
npm run build

# Start production server
npm start

# Clean build cache
rm -rf .next
```

### Adding New Pages
1. Create file in `app/` directory (e.g., `app/reports/page.jsx`)
2. Add navigation link in `components/AdminHeader.jsx`
3. Create API endpoints in backend if needed
4. Update `lib/api.js` with new API calls

### Component Development
- Use functional components with hooks
- Follow existing design patterns from `components/`
- Utilize design system tokens from `lib/design-system.js`
- Ensure responsive design for mobile/tablet/desktop

## Security

- **JWT Authentication**: Token-based with automatic refresh
- **Protected Routes**: All pages require admin authentication
- **MFA Support**: Two-factor authentication for admin accounts
- **CSRF Protection**: Token validation on all mutations
- **Input Validation**: Client-side and server-side validation
- **Rate Limiting**: Handled by backend API
- **Secure Storage**: Sensitive data in httpOnly cookies (if configured)

## Troubleshooting

### Cannot Connect to Backend
```
Error: Network Error
Solution: 
1. Check backend is running (http://localhost:5000)
2. Verify NEXT_PUBLIC_API_URL in .env.local
3. Check CORS configuration in backend
```

### Login Fails
```
Error: Invalid credentials
Solution:
1. Verify admin account exists in database
2. Check password is correct (default: admin123)
3. Ensure admin_users table has been seeded
4. Check backend logs for authentication errors
```

### Crawler Scheduling Not Working
```
Error: Schedule not saving
Solution:
1. Check APScheduler is initialized in backend
2. Verify cron expression is valid
3. Ensure crawler is_active = true
4. Check backend logs for scheduler errors
```

### Build Errors
```
Error: Module not found
Solution:
1. Delete node_modules and .next
2. Run: npm install
3. Run: npm run build
4. Check package.json for missing dependencies
```

## Testing

### Manual Testing Checklist
- [ ] Login with valid credentials
- [ ] Login fails with invalid credentials
- [ ] Dashboard loads with statistics
- [ ] Users page displays list
- [ ] Can search/filter users
- [ ] Can suspend/delete users
- [ ] Crawlers page shows all crawlers
- [ ] Can start/stop crawlers
- [ ] Calendar scheduler opens and saves
- [ ] Statistics page loads charts
- [ ] Settings page saves changes
- [ ] Logout works correctly

### Test Admin Account
Create test admin in database:
```sql
INSERT INTO admin_users (email, username, password_hash)
VALUES (
  'test@admin.local',
  'testadmin',
  '$2b$12$...'  -- bcrypt hash of 'testpass123'
);
```

## Deployment

### Production Build
```bash
# Build optimized bundle
npm run build

# Test production build locally
npm start

# Deploy to server
# - Copy .next folder and dependencies
# - Set NODE_ENV=production
# - Configure reverse proxy (nginx)
```

### Docker Deployment
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build
EXPOSE 3001
CMD ["npm", "start"]
```

### Environment Variables for Production
```env
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NODE_ENV=production
PORT=3001
```

## Performance

- **Code Splitting**: Automatic route-based splitting
- **Image Optimization**: Next.js Image component for logos
- **API Caching**: SWR for data fetching (consider implementing)
- **Bundle Size**: ~500KB gzipped for main bundle
- **Load Time**: <2s initial load, <500ms route transitions

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
- Mobile browsers (iOS Safari 14+, Chrome Android)

## Contributing

### Code Style
- Use ESLint configuration
- Format with Prettier (if configured)
- Follow React best practices
- Write descriptive commit messages

### Pull Request Process
1. Create feature branch from `main`
2. Implement changes with tests
3. Update documentation if needed
4. Submit PR with description
5. Address review comments
6. Merge after approval

## License

Proprietary - All rights reserved

## Support

For issues or questions:
- Check backend logs: `backend/logs/`
- Review browser console for client errors
- Contact development team

---

**Version:** 1.0.0  
**Last Updated:** November 16, 2025  
**Framework:** Next.js 14 + React 18  
**UI Library:** Tailwind CSS  
**State Management:** Zustand
