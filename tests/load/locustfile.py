"""
Load testing configuration for RoleMule.

Run with: locust -f tests/load/locustfile.py --host=http://localhost:8000

Or for headless mode:
locust -f tests/load/locustfile.py --host=http://localhost:8000 --headless -u 10 -r 2 -t 60s

Parameters:
- -u: Number of users to simulate
- -r: Spawn rate (users per second)
- -t: Test duration

Install: pip install locust
"""

import uuid
from locust import HttpUser, task, between, events


# =============================================================================
# CONFIGURATION
# =============================================================================

# Sample data for testing
SAMPLE_JOB_TEXT = """
Software Engineer - Full Stack
Company: LoadTestCorp
Location: Remote
Requirements: Python, JavaScript, React
"""

VALID_BASIC_INFO = {
    "city": "San Francisco",
    "state": "California", 
    "country": "United States",
    "professional_title": "Software Engineer",
    "years_experience": 5,
    "is_student": False,
    "summary": "Experienced software engineer",
}

VALID_SKILLS = {
    "skills": ["Python", "JavaScript", "React", "AWS"]
}

VALID_CAREER_PREFERENCES = {
    "desired_salary_range": {"min": 100000, "max": 200000},
    "desired_company_sizes": ["Medium (51-200 employees)"],
    "job_types": ["Full-time"],
    "work_arrangements": ["Remote"],
    "willing_to_relocate": False,
    "requires_visa_sponsorship": False,
    "has_security_clearance": False,
    "max_travel_preference": "25",
}


# =============================================================================
# USER BEHAVIORS
# =============================================================================


class AuthenticatedUser(HttpUser):
    """
    Simulates an authenticated user browsing the application.
    
    This user:
    1. Registers on startup
    2. Completes profile
    3. Performs various read operations
    4. Occasionally starts workflows
    """
    
    wait_time = between(1, 5)  # Wait 1-5 seconds between tasks
    
    def on_start(self):
        """Called when user starts - register and setup."""
        self.token = None
        self.user_email = f"loadtest_{uuid.uuid4().hex[:8]}@example.com"
        self._register_and_setup()
    
    def _register_and_setup(self):
        """Register user and complete profile."""
        # Register
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": self.user_email,
                "password": "LoadTest123!",
                "confirm_password": "LoadTest123!",
                "full_name": "Load Test User",
            },
        )
        
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self._complete_profile()
        else:
            # If registration fails (e.g., rate limit), try to login
            self._try_login()
    
    def _try_login(self):
        """Try to login if registration fails."""
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.user_email,
                "password": "LoadTest123!",
            },
        )
        if response.status_code == 200:
            self.token = response.json().get("access_token")
    
    def _complete_profile(self):
        """Complete user profile setup."""
        if not self.token:
            return
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Basic info
        self.client.put(
            "/api/v1/profile/basic-info",
            headers=headers,
            json=VALID_BASIC_INFO,
        )
        
        # Work experience
        self.client.put(
            "/api/v1/profile/work-experience",
            headers=headers,
            json={"work_experience": []},
        )
        
        # Skills
        self.client.put(
            "/api/v1/profile/skills-qualifications",
            headers=headers,
            json=VALID_SKILLS,
        )
        
        # Career preferences
        self.client.put(
            "/api/v1/profile/career-preferences",
            headers=headers,
            json=VALID_CAREER_PREFERENCES,
        )
    
    def _get_headers(self):
        """Get auth headers."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    # =========================================================================
    # TASKS - Weighted by frequency
    # =========================================================================
    
    @task(10)
    def view_dashboard(self):
        """View dashboard (most common action)."""
        self.client.get("/dashboard", headers=self._get_headers())
    
    @task(8)
    def list_applications(self):
        """List job applications."""
        self.client.get(
            "/api/v1/applications/",
            headers=self._get_headers(),
        )
    
    @task(5)
    def get_application_stats(self):
        """Get application statistics."""
        self.client.get(
            "/api/v1/applications/stats/overview",
            headers=self._get_headers(),
        )
    
    @task(5)
    def get_profile(self):
        """Get user profile."""
        self.client.get(
            "/api/v1/profile/",
            headers=self._get_headers(),
        )
    
    @task(3)
    def get_profile_status(self):
        """Check profile completion status."""
        self.client.get(
            "/api/v1/profile/status",
            headers=self._get_headers(),
        )
    
    @task(2)
    def verify_token(self):
        """Verify authentication token."""
        self.client.get(
            "/api/v1/auth/verify",
            headers=self._get_headers(),
        )
    
    @task(1)
    def start_workflow(self):
        """
        Start a new workflow (expensive operation - low weight).
        
        Note: This will consume API quota if running against production.
        Set weight to 0 if you want to avoid workflow starts.
        """
        self.client.post(
            "/api/v1/workflow/start",
            headers=self._get_headers(),
            json={"job_text": SAMPLE_JOB_TEXT},
        )


class UnauthenticatedUser(HttpUser):
    """
    Simulates unauthenticated users hitting public endpoints.
    
    This tests the public-facing parts of the application.
    """
    
    wait_time = between(1, 3)
    
    @task(10)
    def view_homepage(self):
        """View the homepage."""
        self.client.get("/")
    
    @task(5)
    def view_login_page(self):
        """View the login page."""
        self.client.get("/auth/login")
    
    @task(5)
    def view_register_page(self):
        """View the registration page."""
        self.client.get("/auth/register")
    
    @task(3)
    def health_check(self):
        """Hit the health check endpoint."""
        self.client.get("/health")
    
    @task(2)
    def check_oauth_status(self):
        """Check OAuth status (public endpoint)."""
        self.client.get("/api/v1/auth/oauth/status")
    
    @task(1)
    def attempt_protected_endpoint(self):
        """
        Attempt to access protected endpoint without auth.
        This should return 401/403 quickly.
        """
        self.client.get("/api/v1/profile/")


class APIStressUser(HttpUser):
    """
    Simulates heavy API usage for stress testing.
    
    Use this to find breaking points and rate limit effectiveness.
    """
    
    wait_time = between(0.1, 0.5)  # Very fast requests
    
    def on_start(self):
        """Register and get token."""
        self.user_email = f"stress_{uuid.uuid4().hex[:8]}@example.com"
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": self.user_email,
                "password": "StressTest123!",
                "confirm_password": "StressTest123!",
                "full_name": "Stress Test User",
            },
        )
        
        if response.status_code == 200:
            self.token = response.json().get("access_token")
        else:
            self.token = None
    
    def _get_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    @task(5)
    def rapid_list_applications(self):
        """Rapidly list applications."""
        self.client.get("/api/v1/applications/", headers=self._get_headers())
    
    @task(3)
    def rapid_get_stats(self):
        """Rapidly get stats."""
        self.client.get("/api/v1/applications/stats/overview", headers=self._get_headers())
    
    @task(2)
    def rapid_health_check(self):
        """Rapid health checks."""
        self.client.get("/health")


# =============================================================================
# EVENT HOOKS
# =============================================================================


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    print("\n" + "="*60)
    print("LOAD TEST STARTING")
    print("="*60)
    print(f"Target host: {environment.host}")
    print(f"User classes: {[cls.__name__ for cls in environment.user_classes]}")
    print("="*60 + "\n")


@events.test_stop.add_listener  
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    print("\n" + "="*60)
    print("LOAD TEST COMPLETED")
    print("="*60 + "\n")


# =============================================================================
# USAGE EXAMPLES
# =============================================================================

"""
USAGE EXAMPLES:

1. Interactive mode (with web UI):
   locust -f tests/load/locustfile.py --host=http://localhost:8000
   Then open http://localhost:8089 in browser

2. Headless mode (quick test):
   locust -f tests/load/locustfile.py --host=http://localhost:8000 \\
       --headless -u 10 -r 2 -t 30s

3. Specific user class only:
   locust -f tests/load/locustfile.py --host=http://localhost:8000 \\
       AuthenticatedUser --headless -u 5 -r 1 -t 60s

4. Stress test mode:
   locust -f tests/load/locustfile.py --host=http://localhost:8000 \\
       APIStressUser --headless -u 50 -r 10 -t 60s

5. Output to CSV:
   locust -f tests/load/locustfile.py --host=http://localhost:8000 \\
       --headless -u 20 -r 5 -t 120s --csv=results/loadtest

PARAMETERS:
- -u, --users: Total number of concurrent users
- -r, --spawn-rate: Users spawned per second
- -t, --run-time: Test duration (e.g., 30s, 5m, 1h)
- --headless: Run without web UI
- --csv: Output results to CSV files
- --html: Generate HTML report

NOTES:
- The workflow start task is set to low weight (1) to avoid excessive API costs
- Set workflow task weight to 0 for cost-free load testing
- Use APIStressUser class to test rate limiting effectiveness
"""
