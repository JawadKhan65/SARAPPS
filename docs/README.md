# Frontend - Shoe Type Identification System

## Overview

The frontend is a Next.js application that provides a modern, responsive user interface for shoe identification through image upload and matching against a comprehensive database.

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

**Access:** http://localhost:3000

**Test User Login:**
- Email: `user1@example.com`
- Password: `password123`

## Project Structure

```
frontend/
├── app/
│   ├── page.jsx                    # Landing/home page
│   ├── layout.jsx                  # Root layout with header
│   ├── globals.css                 # Global styles
│   ├── login/
│   │   └── page.jsx               # Login page
│   ├── register/
│   │   └── page.jsx               # Registration page
│   ├── dashboard/
│   │   └── page.jsx               # Main dashboard (upload & identify)
│   ├── matches/
│   │   └── page.jsx               # Match history with filtering
│   └── settings/
│       └── page.jsx               # User settings & profile
├── components/
│   ├── AuthProvider.jsx            # Auth initialization wrapper
│   ├── Header.jsx                  # Navigation header
│   ├── ProtectedRoute.jsx          # Route protection HOC
│   ├── MatchCard.jsx               # Match result display component
│   ├── ImageUpload.jsx             # File upload with camera support
│   └── ui/                         # Reusable UI components
├── lib/
│   ├── api.js                      # Axios API client
│   ├── store.js                    # Zustand state management
│   └── utils.js                    # Utility functions
├── public/                          # Static assets (logos, favicons)
├── package.json                     # Dependencies
├── tailwind.config.js               # Tailwind CSS configuration
├── next.config.ts                   # Next.js configuration
└── tsconfig.json                    # TypeScript configuration
```

## Features

### 1. Landing Page (`/`)
- **Hero Section**: Compelling introduction to shoe identification
- **Features Overview**: Key capabilities and benefits
- **How It Works**: Step-by-step process explanation
- **Call to Action**: Register/Login buttons
- **Responsive Design**: Mobile, tablet, desktop optimized

### 2. Authentication

#### Login (`/login`)
- Email/password authentication
- "Remember Me" option for persistent sessions
- Forgot password link
- Validation feedback
- Redirect to dashboard after login

#### Register (`/register`)
- Email, username, password fields
- Password strength indicator
- Terms & conditions acceptance
- Email validation
- Duplicate email checking
- Automatic login after registration

### 3. Dashboard (`/dashboard`)
**Main Feature**: Upload shoe images for identification

**Upload Methods:**
- **File Upload**: Drag & drop or click to browse
- **Camera Capture**: Take photo directly (mobile/desktop)
- **Paste Image**: Ctrl+V to paste from clipboard

**Image Processing:**
- Format validation (JPEG, PNG, WebP)
- Size limit enforcement (10MB max)
- Preview before submission
- Crop/resize options (planned)

**Identification Process:**
1. Upload shoe sole image
2. Backend extracts 5 features (LBP, Edge, Color, CLIP, Line Tracing)
3. Vector similarity search against database
4. Return ranked matches with confidence scores

**Results Display:**
- Top matches with confidence scores:
  - 🟢 Excellent (90-100%)
  - 🟡 Good (75-89%)
  - 🟠 Fair (60-74%)
  - 🔴 Poor (0-59%)
- Shoe details: Brand, model, size, color
- Side-by-side image comparison
- "Confirm Match" or "Not a Match" feedback
- View product details link (if available)

### 4. Match History (`/matches`)
- **List View**: All previous shoe identifications
- **Filters**:
  - Date range picker
  - Confidence level filter
  - Brand/model search
  - Sort by date/confidence
- **Match Details**: Click to view full details
- **Re-identify**: Upload new image for comparison
- **Export History**: Download as CSV
- **Delete Matches**: Remove unwanted entries

### 5. User Settings (`/settings`)

#### Profile Tab
- Update email, username
- Profile photo upload
- Group association display
- Dark mode toggle
- Language preference (planned)

#### Security Tab
- Change password with current password validation
- Two-factor authentication setup (TOTP)
- View active sessions
- Delete account (with confirmation)

#### Preferences Tab
- Email notifications toggle
- Match confidence threshold
- Display preferences
- Privacy settings

## API Integration

### Authentication
```javascript
// Register
POST /api/auth/register
Body: { email, username, password }
Response: { success, user, token }

// Login
POST /api/auth/login
Body: { email, password, remember_me }
Response: { success, token, user }

// Refresh token
POST /api/auth/refresh
Headers: { Authorization: Bearer <token> }
Response: { token }

// Logout
POST /api/auth/logout
```

### User Management
```javascript
// Get profile
GET /api/user/profile
Headers: { Authorization: Bearer <token> }
Response: { user, group }

// Update profile
PUT /api/user/profile
Body: { username, dark_mode, language }

// Upload profile image
POST /api/user/upload-image
Body: FormData { image: File }

// Change password
POST /api/user/change-password
Body: { current_password, new_password }

// Delete account
DELETE /api/user/account
Body: { password }
```

### Shoe Identification
```javascript
// Upload and identify
POST /api/user/upload-image
Body: FormData { image: File }
Response: { 
  image_id, 
  image_url, 
  uploaded_at,
  message 
}

// Get matches
POST /api/matches/identify
Body: { image_id }
Response: {
  matches: [
    {
      shoe_id,
      brand,
      model,
      confidence_score,
      similarity_score,
      image_url,
      product_url
    }
  ],
  processing_time
}

// Confirm match
POST /api/matches/confirm
Body: { match_id, is_correct }

// Get match history
GET /api/matches/history?page=1&limit=20
Response: { matches, total, page, pages }
```

## State Management

**Zustand Store** (`lib/store.js`):
```javascript
{
  // Auth state
  isAuthenticated: boolean,
  user: {
    id: number,
    email: string,
    username: string,
    dark_mode: boolean,
    group_id: number,
    profile_image_url: string
  } | null,
  token: string | null,
  
  // Actions
  login: (email, password, rememberMe) => Promise<void>,
  register: (email, username, password) => Promise<void>,
  logout: () => void,
  checkAuth: () => void,
  updateUser: (userData) => void
}
```

**LocalStorage Persistence**:
- User credentials persist across sessions
- Automatic token refresh
- Clear on logout

## Styling

**Tailwind CSS** with custom configuration:
- **Colors**: Blue primary (#3B82F6), gradient backgrounds
- **Typography**: Inter font family
- **Components**: Pre-built card, button, input styles
- **Responsive**: Mobile-first breakpoints (sm, md, lg, xl)
- **Animations**: Smooth transitions, hover effects
- **Dark Mode**: Toggle in user settings

## Environment Variables

Create `.env.local`:
```env
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:5000

# App Settings
NEXT_PUBLIC_APP_NAME=Shoe Type Identification System
NEXT_PUBLIC_MAX_FILE_SIZE=10485760  # 10MB in bytes
NEXT_PUBLIC_ALLOWED_FORMATS=image/jpeg,image/png,image/webp
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

# Type checking
npm run type-check

# Clean build
rm -rf .next
```

### Adding New Features

#### Add New Page
1. Create file in `app/` (e.g., `app/feedback/page.jsx`)
2. Add link in `components/Header.jsx`
3. Add API calls in `lib/api.js` if needed

#### Add New Component
1. Create in `components/` (e.g., `components/ShoeCard.jsx`)
2. Import and use in pages
3. Add PropTypes or TypeScript types

#### Add API Endpoint
1. Add function in `lib/api.js`:
```javascript
export const myNewEndpoint = (data) => 
  api.post('/endpoint', data);
```
2. Use in components with error handling

## Image Upload Implementation

**Component**: `components/ImageUpload.jsx`

**Features**:
- Drag & drop zone
- File browser
- Camera capture (mobile/desktop)
- Image preview
- Progress indicator
- Error handling

**Usage**:
```jsx
<ImageUpload
  onUpload={(file) => handleUpload(file)}
  maxSize={10 * 1024 * 1024}  // 10MB
  acceptedFormats={['image/jpeg', 'image/png']}
/>
```

**Camera Integration**:
```javascript
navigator.mediaDevices.getUserMedia({ video: true })
  .then(stream => {
    videoRef.current.srcObject = stream;
  })
  .catch(err => {
    console.error('Camera access denied:', err);
  });
```

## Security

- **JWT Authentication**: Token stored in localStorage
- **Protected Routes**: Automatic redirect if not authenticated
- **Token Refresh**: Automatic refresh before expiration
- **XSS Protection**: Input sanitization
- **CSRF Protection**: Token validation
- **File Upload Validation**: Type, size, content checks
- **HTTPS**: Required for production

## Performance Optimization

- **Code Splitting**: Automatic by Next.js
- **Image Optimization**: next/image component
- **Lazy Loading**: Dynamic imports for heavy components
- **Caching**: API response caching with SWR (consider)
- **Bundle Size**: ~600KB gzipped
- **Load Time**: <2s FCP, <3s LCP

## Responsive Design

### Breakpoints
- **Mobile**: 320px - 640px (sm)
- **Tablet**: 641px - 1024px (md, lg)
- **Desktop**: 1025px+ (xl, 2xl)

### Mobile Features
- Touch-friendly buttons (min 44x44px)
- Swipe gestures for image carousel
- Camera integration
- Responsive navigation (hamburger menu)
- Bottom tab bar (planned)

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
- Mobile browsers (iOS Safari 14+, Chrome Android)

## Accessibility

- **ARIA Labels**: Screen reader support
- **Keyboard Navigation**: Tab, Enter, Space
- **Focus Indicators**: Visible focus states
- **Color Contrast**: WCAG AA compliance
- **Alt Text**: Images with descriptive text
- **Semantic HTML**: Proper heading hierarchy

## Testing

### Manual Testing Checklist
- [ ] Registration with valid/invalid data
- [ ] Login with valid/invalid credentials
- [ ] "Remember Me" persists session
- [ ] Dashboard loads correctly
- [ ] Image upload (file, drag-drop, camera)
- [ ] Image identification returns results
- [ ] Match confidence scores display correctly
- [ ] Match history loads with filters
- [ ] Settings save successfully
- [ ] Password change works
- [ ] Logout clears session
- [ ] Protected routes redirect when logged out

### Test User Accounts
```sql
-- Create test users in database
INSERT INTO users (email, username, password_hash, group_id)
VALUES 
  ('test1@test.com', 'testuser1', '$2b$12$...', 1),
  ('test2@test.com', 'testuser2', '$2b$12$...', 1);
```

## Troubleshooting

### Cannot Connect to Backend
```
Error: Network Error
Solution:
1. Check backend is running (http://localhost:5000)
2. Verify NEXT_PUBLIC_API_URL in .env.local
3. Check CORS settings in backend
4. Check browser console for errors
```

### Images Not Uploading
```
Error: File upload failed
Solution:
1. Check file size (<10MB)
2. Verify file format (JPEG, PNG, WebP)
3. Check backend upload endpoint is working
4. Verify CORS allows multipart/form-data
5. Check backend logs for errors
```

### Authentication Issues
```
Error: Token expired or invalid
Solution:
1. Clear localStorage and login again
2. Check token refresh logic in api.js
3. Verify backend JWT secret matches
4. Check token expiration time
```

### Build Errors
```
Error: Module not found
Solution:
1. Delete node_modules and .next
2. Run: npm install
3. Run: npm run build
4. Check package.json dependencies
```

## Deployment

### Production Build
```bash
# Build optimized bundle
npm run build

# Test production build locally
npm start

# Verify build
# - Check .next folder created
# - No console errors
# - All routes work
```

### Docker Deployment
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

### Environment Variables for Production
```env
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NODE_ENV=production
PORT=3000
```

### Reverse Proxy (Nginx)
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

## Contributing

### Code Style
- Use ESLint configuration
- Format with Prettier
- Follow React best practices
- Write descriptive commit messages

### Component Guidelines
- Functional components with hooks
- PropTypes or TypeScript for props
- Destructure props
- Extract reusable logic to hooks
- Keep components small and focused

## Known Issues

1. **Camera on iOS Safari**: Requires HTTPS in production
2. **Large Image Upload**: May timeout on slow connections
3. **Dark Mode**: Incomplete implementation
4. **Offline Support**: Not yet implemented (PWA planned)

## Future Enhancements

- [ ] Progressive Web App (PWA)
- [ ] Offline mode with service worker
- [ ] Image crop/rotate before upload
- [ ] Batch upload multiple images
- [ ] Social sharing of matches
- [ ] Shoe collection management
- [ ] Wishlist feature
- [ ] Notification system
- [ ] Chat support
- [ ] Multi-language support

## License

Proprietary - All rights reserved

## Support

For issues or questions:
- Check backend logs: `backend/logs/`
- Review browser console
- Contact development team

---

**Version:** 1.0.0  
**Last Updated:** November 16, 2025  
**Framework:** Next.js 14 + React 18  
**UI Library:** Tailwind CSS  
**State Management:** Zustand
