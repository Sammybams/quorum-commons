# Pre-Demo QA Checklist

## Environment
- [ ] Backend starts cleanly on `:8000`
- [ ] Frontend starts cleanly on `:3000`
- [ ] MongoDB connection is valid
- [ ] `ANTHROPIC_API_KEY` is present
- [ ] Google OAuth env values are present

## Landing Page
- [ ] Top nav anchors work
- [ ] Pricing cards show Starter / Growth / Pro correctly
- [ ] Light mode and dark mode both render cleanly
- [ ] Wordmark is visible in both themes

## Auth
- [ ] Standard sign-in works
- [ ] Demo login opens the seeded demo workspace
- [ ] Forgot-password and verify-email screens still load

## Workspace
- [ ] Sidebar and main area scroll independently
- [ ] Navigation between Dashboard / Members / Events / Meetings / Campaigns is fast
- [ ] Profile menu opens and closes correctly
- [ ] Brand text is visible in the shell

## Demo Workspace Data
- [ ] Members list is populated
- [ ] Events list is populated
- [ ] Meetings page has at least one meeting with minutes
- [ ] Dues page has a cycle and payment records
- [ ] Campaigns page has streams and contributions
- [ ] Budgets page has at least one budget with lines
- [ ] Announcements page has published updates
- [ ] Links page has tracked short links
- [ ] Reports page has at least one completed audit report

## Integrations / AI
- [ ] Google integrations page loads
- [ ] Gmail invitation flow is visible
- [ ] Meeting AI minutes page renders without errors
- [ ] Analytics report page renders scorecard, summary, and recommendations
- [ ] Print / Save PDF opens a clean printable report view

## Final Demo Hygiene
- [ ] Browser is already signed into the correct environment
- [ ] Unrelated test workspaces are not the default path
- [ ] Incognito window is ready for public or invite flows
- [ ] Vercel deployment matches local behavior
