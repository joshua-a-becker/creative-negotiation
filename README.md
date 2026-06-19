# ZOPA vs Complexity Video Negotiation Platform

A research-grade experimental platform for studying negotiation dynamics through controlled video-based experiments. Built with Empirica.ly and Daily.co.

**Principal Investigator:** Joshua Becker, University College London (UCL)
**Contact:** joshua.becker@ucl.ac.uk
**Production URL:** https://platform.negotiation.education

---

## Table of Contents

- [Overview](#overview)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Running the Application](#running-the-application)
- [Experiment Design](#experiment-design)
- [Architecture Deep Dive](#architecture-deep-dive)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Data Collection](#data-collection)
- [Development Notes](#development-notes)
- [Security Considerations](#security-considerations)

---

## Overview

This platform implements a two-party video negotiation experiment where participants:

1. **Preparation (5 min):** Read role materials and understand their scoring objectives
2. **Negotiation (30 min):** Video conference with partner while referencing materials and using chat
3. **Data Collection:** Video recordings, transcripts, chat logs, and interaction data saved for analysis

### Negotiation Scenario

Participants negotiate a space-sharing agreement between two organizations:
- **Community Harvest Food Bank**
- **Citizens' Resource Hub**

They must agree on 6 dimensions:
- Location choice (4 options)
- Renovation cost split
- Rent split percentage
- Lease term length
- Evening/weekend access
- Space allocation

Each role has unique scoring preferences (asymmetric information) creating integrative bargaining opportunities where trades can benefit both parties.

---

## Technology Stack

### Frontend (`/client`)
- **React** 18.2.0 - UI framework
- **Vite** 5.1.4 - Build tool and dev server
- **UnoCSS** 0.58.5 - Utility-first CSS framework
- **@daily-co/daily-js** 0.85.0 - Video conferencing SDK
- **react-markdown** 10.1.0 - Markdown rendering for role narratives
- **lucide-react** 0.263.1 - Icon library
- **@empirica/core** 1.12.5 - Experiment framework

### Backend (`/server`)
- **Node.js** 20.11.1
- **esbuild** 0.14.47 - Bundling and minification
- **nodemon** 3.1.11 - Development hot reload
- **js-yaml** 4.1.1 - YAML configuration parsing
- **@empirica/core** 1.12.5 - Experiment server

### Infrastructure
- **Empirica.ly** - Multiplayer experiment framework
- **Daily.co** - Video conferencing with cloud recording/transcription
- **Caddy** - Reverse proxy with automatic HTTPS
- **DigitalOcean** - Hosting (209.97.131.189)

---

## Project Structure

```
zopa-vs-complexity/
├── client/                          # Frontend React application
│   ├── src/
│   │   ├── components/
│   │   │   ├── CustomChat.jsx       # Real-time text chat
│   │   │   ├── MaterialsPanel.jsx   # Role materials (narrative/scoresheet/calculator)
│   │   │   ├── Profile.jsx          # Stage name and timer display
│   │   │   ├── Timer.jsx            # Countdown timer
│   │   │   └── VideoChat.jsx        # Daily.co video integration
│   │   ├── intro-exit/
│   │   │   ├── CustomConsent.jsx    # Multi-page onboarding + consent gate (intro, time commitment, difficulty note, consent form)
│   │   │   ├── DisplayNameEntry.jsx # Participant name input
│   │   │   ├── AutoPlayerIdForm.jsx # Auto-generate participant IDs
│   │   │   └── ExitSurvey.jsx       # Post-experiment survey (empty)
│   │   ├── stages/
│   │   │   ├── ReadRole.jsx         # Stage 1: Role preparation
│   │   │   └── VideoNegotiate.jsx   # Stage 2: Video negotiation
│   │   ├── App.jsx                  # Root component + Daily.co call management (1000+ lines)
│   │   ├── Game.jsx                 # Empirica game wrapper
│   │   ├── Stage.jsx                # Stage router
│   │   ├── index.jsx                # App entry point
│   │   └── roles.json               # Role definitions and scoresheets
│   ├── public/                      # Static assets
│   ├── package.json
│   └── vite.config.js               # Vite configuration
│
├── server/                          # Backend Empirica server
│   ├── src/
│   │   ├── callbacks.js             # Game lifecycle logic (onGameStart, onStageStart)
│   │   └── index.js                 # Server entry point
│   ├── package.json
│   └── esbuild.config.js            # Build configuration
│
├── .empirica/                       # Experiment configuration
│   ├── empirica.toml                # Auth and app settings
│   ├── treatments.yaml              # Experimental conditions
│   ├── lobbies.yaml                 # Participant matching configuration
│   ├── local.toml                   # Local development overrides
│   └── REVISED_ROLES.md             # Role documentation
│
├── deploy.sh                        # Production deployment script
├── delete-recordings.sh             # Clean up Daily.co recordings
└── delete-transcripts.sh            # Clean up Daily.co transcripts
```

---

## Setup & Installation

### Prerequisites
- **Node.js** 20.11.1 or higher
- **npm** (comes with Node.js)
- **Empirica CLI** (install globally: `npm install -g @empirica/empirica`)
- **Daily.co account** with API keys

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd zopa-vs-complexity
   ```

2. **Install client dependencies:**
   ```bash
   cd client
   npm install
   ```

3. **Install server dependencies:**
   ```bash
   cd ../server
   npm install
   ```

4. **Configure Daily.co API keys:**

   Edit `server/src/callbacks.js` and replace the API keys:
   ```javascript
   // Line ~30: Room creation/token generation
   const DAILY_API_KEY = "your-daily-api-key-here";

   // Line ~120: Presence tracking
   const dailyApiKey = "your-daily-api-key-here";
   ```

   **Security Note:** In production, use environment variables instead of hardcoding.

5. **Configure Empirica authentication:**

   Edit `.empirica/empirica.toml`:
   ```toml
   [auth]
   srtoken = "your-secret-token"

   [[auth.users]]
   name = "Admin"
   username = "admin"
   password = "your-secure-password"
   ```

---

## Running the Application

### Development Mode

**Terminal 1 - Start Empirica server:**
```bash
cd server
npm run dev
# or for auto-restart on changes:
npm run watch
```

**Terminal 2 - Start Vite dev server:**
```bash
cd client
npm run dev
```

**Access points:**
- **Participant interface:** http://localhost:8844
- **Admin dashboard:** http://localhost:3000/admin
  - Login with credentials from `.empirica/empirica.toml`

### Testing Flow

1. Navigate to admin dashboard (http://localhost:3000/admin)
2. Create a new batch with desired treatment
3. Start the batch
4. Open participant interface in two browser windows (use incognito/different browsers)
5. Each participant will:
   - Complete introduction and consent
   - Enter display name
   - Read role materials (Stage 1)
   - Negotiate via video (Stage 2)

### URL Parameters

- `?skipIntro=T` - Skip introduction steps (for testing)
- `?studentId=12345` - Set participant ID (auto-generates participantKey)

---

## Experiment Design

### Game Structure

Defined in `server/src/callbacks.js`:

```
Game (2 players)
  └─ Round: "Negotiation Game"
      ├─ Stage 1: "Read Negotiation Role"
      │   Duration: 300 seconds (5 minutes)
      │   Purpose: Understand role, scoresheet, and BATNA
      │
      └─ Stage 2: "Time To Negotiate"
          Duration: 1800 seconds (30 minutes)
          Purpose: Video negotiation with partner
```

### Roles

Two roles with asymmetric scoring preferences:

**Community Harvest Food Bank:**
- Reservation Point (BATNA): 170 points
- Unique priorities and scoring across 6 dimensions

**Citizens' Resource Hub:**
- Reservation Point (BATNA): 210 points
- Different scoring preferences creating trade opportunities

Full role definitions in `client/src/roles.json` and `.empirica/REVISED_ROLES.md`.

### Treatments

Configured in `.empirica/treatments.yaml`:

**Factors:**
- `playerCount`: Number of players (currently using 2)
- `readRoleTime`: Preparation time in seconds (default: 300)
- `negotiateTime`: Negotiation time in seconds (default: 1800)

**Current treatments:** Support 1-13 player configurations (though only 2-player is used).

### Lobbies

Three lobby configurations in `.empirica/lobbies.yaml`:

1. **Default shared fail** - Shared lobby, 5min timeout, fail if incomplete
2. **Default shared ignore** - Shared lobby, 5min timeout, ignore incomplete
3. **Default individual** - Individual progression (no matching required)

---

## Architecture Deep Dive

### Empirica.ly Framework

Empirica provides:
- **Game state management** - Centralized state synchronized across clients
- **Player matching** - Lobby system for pairing participants
- **Stage progression** - Automatic timing and transitions
- **Data persistence** - All game state saved to database
- **Admin dashboard** - Monitor experiments, manage batches

**Server-side callbacks** (`server/src/callbacks.js`):

```javascript
Empirica.on("game", (ctx, { game }) => {
  // onGameStart: Initialize Daily.co room, assign roles
  game.on("start", ({ game }) => {
    // Create video room
    // Generate meeting tokens
    // Assign roles and scoresheets
  });

  // onStageStart: Monitor participant presence
  game.on("stage", ({ stage }) => {
    // Track disconnections
    // Handle participant abandonment
  });
});
```

**Client-side integration** (`client/src/`):

```jsx
// App.jsx wraps everything in EmpiricaParticipant
<EmpiricaParticipant {...empiricaConfig}>
  <Game /> {/* Game.jsx routes to current stage */}
</EmpiricaParticipant>

// Access game state with hooks
const player = usePlayer();
const game = useGame();
const stage = useStage();

// Update state
player.set("score", 150);
game.set("chatMessages", messages);
```

### Daily.co Video Integration

**Architecture:** DailyCallContext provider in `App.jsx` (1000+ lines)

**Call Lifecycle:**

1. **Permission Request** (`MediaPermissionGate.jsx`)
   - Request camera/microphone access
   - Enumerate available devices
   - Store device preferences
   - Preview media stream

2. **Call Creation** (`App.jsx`)
   ```javascript
   const callObject = DailyIframe.createCallObject({
     audioSource: selectedAudioDevice,
     videoSource: selectedVideoDevice
   });

   await callObject.join({
     url: roomUrl,
     token: dailyMeetingToken,
     userName: displayName
   });
   ```

3. **Stream Management**
   - Track all participants in `remoteParticipants` state
   - Listen for `participant-joined`, `participant-updated`, `track-started` events
   - Attach audio/video tracks to HTML elements
   - Implement recovery mechanisms for dropped streams

4. **Recording & Transcription**
   - Auto-start on `joined-meeting` event
   - Cloud recording with transcription enabled
   - Stop when participant leaves

**Stream Recovery Mechanisms:**

```javascript
// Fast polling: 500ms for first 10 seconds
// Slow polling: 2s for 4+ minutes
// Dead stream detection: Clean up ended tracks
// Manual refresh: User-triggered stream reload
```

### Component Communication

**State Flow:**

```
DailyCallContext (App.jsx)
  ├─ mediaStream → MediaPermissionGate
  ├─ callObject → VideoChat
  ├─ remoteParticipants → RemoteVideoComponent
  └─ isAudioEnabled/isVideoEnabled → Audio/video controls

EmpiricaContext
  ├─ player → Profile, MaterialsPanel, CustomChat
  ├─ game → CustomChat (messages), VideoNegotiate
  └─ stage → Profile (timer), Stage routing
```

---

## Configuration

### Empirica Configuration Files

**`.empirica/empirica.toml`** - Basic app settings:
```toml
name = "VideoChatApp"

[auth]
srtoken = "your-secret-token"

[[auth.users]]
name = "Admin"
username = "admin"
password = "your-password"
```

**`.empirica/treatments.yaml`** - Experimental conditions:
```yaml
factors:
  - name: playerCount
    values: [2]
  - name: readRoleTime
    values: [300]  # 5 minutes
  - name: negotiateTime
    values: [1800]  # 30 minutes

treatments:
  - name: "Standard 2-player"
    factors:
      playerCount: 2
      readRoleTime: 300
      negotiateTime: 1800
```

**`.empirica/lobbies.yaml`** - Matching configuration:
```yaml
lobbies:
  - name: "Default shared fail"
    kind: shared
    strategy: fail
    timeout: 300s  # 5 minutes
```

**`.empirica/local.toml`** - Development overrides:
```toml
# Override production settings for local dev
[server]
addr = "localhost:3000"
```

### Client Configuration

**`client/vite.config.js`**:
```javascript
export default defineConfig({
  server: {
    port: 8844
  },
  plugins: [
    react(),
    UnoCSS()
  ]
})
```

**`client/uno.config.js`** - Tailwind-compatible utility CSS.

### Role Configuration

**`client/src/roles.json`** - Full role definitions:
```json
{
  "Community Harvest Food Bank": {
    "narrative": "...",
    "scoresheet": {
      "Location": {...},
      "Renovation Cost": {...},
      // etc.
    },
    "BATNA": "...",
    "RP": 170
  },
  "Citizens' Resource Hub": {...}
}
```

---

## Deployment

### Production Deployment

**Server:** DigitalOcean droplet at 209.97.131.189
**Domain:** platform.negotiation.education
**SSL:** Automatic via Caddy + Let's Encrypt

**Deployment Script** (`deploy.sh`):

```bash
#!/bin/bash

# 1. Bundle application
empirica bundle

# 2. Transfer to server
scp VideoChatApp.tar.zst root@209.97.131.189:/root/

# 3. SSH and start server
ssh root@209.97.131.189 "empirica serve VideoChatApp.tar.zst"
```

**Steps:**

1. **Bundle locally:**
   ```bash
   empirica bundle
   # Creates VideoChatApp.tar.zst
   ```

2. **Transfer to server:**
   ```bash
   scp VideoChatApp.tar.zst root@209.97.131.189:/root/
   ```

3. **Start Empirica server:**
   ```bash
   ssh root@209.97.131.189
   empirica serve VideoChatApp.tar.zst
   # Runs on localhost:3000
   ```

4. **Caddy reverse proxy:**
   - Configured to route https://platform.negotiation.education → localhost:3000
   - Auto-renewal of SSL certificates

### Caddy Configuration

```caddy
platform.negotiation.education {
    reverse_proxy localhost:3000
    tls {
        email joshua.becker@ucl.ac.uk
    }
}
```

---

## Data Collection

### Collected Data

1. **Video Recordings**
   - Stored in Daily.co cloud
   - Format: MP4
   - Accessible via Daily.co dashboard or API

2. **Transcripts**
   - Automatic speech-to-text via Daily.co
   - JSON format with timestamps and speaker identification
   - Stored in Daily.co cloud

3. **Chat Messages**
   - Stored in Empirica game state
   - Structure: `{playerId, displayName, text, timestamp}`
   - Accessible via Empirica data export

4. **Game State**
   - All player attributes (role, scores, display names)
   - Stage timestamps and progression
   - Participant presence tracking
   - Exportable from Empirica admin dashboard

### Data Export

**Empirica data:**
```bash
# From admin dashboard
# Export → CSV/JSON download
```

**Daily.co recordings:**
```bash
# Using Daily.co API
GET https://api.daily.co/v1/recordings
GET https://api.daily.co/v1/recordings/:recording-id
```

**Daily.co transcripts:**
```bash
GET https://api.daily.co/v1/transcription/:transcription-id
```

### Data Cleanup Scripts

**`delete-recordings.sh`** - Remove saved recordings:
```bash
#!/bin/bash
# Calls Daily.co API to delete all recordings
# Use between experimental sessions
```

**`delete-transcripts.sh`** - Remove saved transcripts:
```bash
#!/bin/bash
# Calls Daily.co API to delete all transcripts
```

---

## Development Notes

### Key Files to Understand

1. **`client/src/App.jsx`** (1000+ lines)
   - DailyCallContext provider
   - Video call lifecycle management
   - Stream recovery mechanisms
   - Most complex component

2. **`server/src/callbacks.js`**
   - Game initialization logic
   - Daily.co room creation
   - Role assignment
   - Participant monitoring

3. **`client/src/stages/VideoNegotiate.jsx`**
   - Main negotiation interface
   - Layout: MaterialsPanel + VideoChat + CustomChat

4. **`client/src/components/MaterialsPanel.jsx`**
   - Tabbed interface for role materials
   - Calculator component for score calculation

### Development Features

**Skip intro in testing:**
```
http://localhost:8844?skipIntro=T
```

**Set participant ID:**
```
http://localhost:8844?studentId=test123
```

**Skip stage (dev mode only):**
- "Skip Stage" button appears in development builds
- Located in `Profile.jsx` component

### Testing Checklist

- [ ] Camera/microphone permissions granted
- [ ] Device selection works (multiple cameras/mics)
- [ ] Video appears for both local and remote participants
- [ ] Audio working in both directions
- [ ] Chat messages send and receive
- [ ] Timer counts down correctly
- [ ] Stage auto-advances when timer expires
- [ ] Calculator shows correct scores
- [ ] Materials panel tabs all display
- [ ] Recording starts automatically
- [ ] Transcription enabled

### Performance Considerations

**Memoized components:**
```jsx
// LocalVideoComponent and RemoteVideoComponent use custom comparison
React.memo(LocalVideoComponent, (prevProps, nextProps) => {
  // Only re-render if participant object changes
  return prevProps.participant === nextProps.participant;
});
```

**Adaptive polling:**
- Fast polling (500ms) for first 10 seconds
- Slow polling (2s) for 4+ minutes
- Reduces CPU usage while maintaining responsiveness

**Lazy loading:**
- Messages in CustomChat only render visible items
- Scrolling triggers loading more messages

### Common Issues

**Video stream not appearing:**
- Check browser permissions (camera/microphone)
- Try manual refresh button in VideoChat
- Check console for Daily.co errors
- Verify Daily.co API keys are valid

**Stage not advancing:**
- Check timer in Profile component
- Verify stage durations in `.empirica/treatments.yaml`
- Check for JavaScript errors in console

**Participants not matched:**
- Check lobby configuration in `.empirica/lobbies.yaml`
- Verify batch is started in admin dashboard
- Check player count matches treatment

**Recording not starting:**
- Verify Daily.co API key has recording permissions
- Check Daily.co account has recording enabled
- Look for errors in server logs

---

## Security Considerations

### Current Security Issues

1. **Hardcoded API keys** in `server/src/callbacks.js`
   - Daily.co API keys should be in environment variables
   - Fix: Use `process.env.DAILY_API_KEY`

2. **Hardcoded admin password** in `.empirica/empirica.toml`
   - "catscatscats" is not secure for production
   - Change before deployment

3. **No CORS configuration**
   - May need to restrict origins in production

### Best Practices Implemented

1. **Explicit consent** - CustomConsent.jsx requires agreement on its final page
2. **Recording disclosure** - CustomConsent's intro and consent pages disclose video recording
3. **Token-based access** - Daily.co uses meeting tokens (not public URLs)
4. **Empirica auth** - Admin dashboard requires login
5. **HTTPS** - Caddy handles SSL/TLS automatically

### Compliance

**Research Ethics:**
- Consent form mentions PI and contact info
- Participants informed about data usage
- Video recording disclosed upfront

**GDPR Considerations:**
- Participant IDs auto-generated (can be pseudonymous)
- Data stored for research purposes (legal basis: research)
- Consider data retention policy for Daily.co recordings

---

## Additional Resources

**Empirica Documentation:** https://empirica.ly/docs
**Daily.co Documentation:** https://docs.daily.co
**React Documentation:** https://react.dev
**Vite Documentation:** https://vitejs.dev

**Support:**
- Joshua Becker: joshua.becker@ucl.ac.uk
- Empirica Discord: https://discord.gg/empirica
- Daily.co Support: help@daily.co

---

## License

[Specify license if applicable]

## Acknowledgments

Built with Empirica.ly (https://empirica.ly) - Open-source framework for multiplayer behavioral experiments.

Video conferencing powered by Daily.co (https://daily.co).
