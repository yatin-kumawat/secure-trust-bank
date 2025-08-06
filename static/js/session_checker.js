function setupSessionExpiry(expiryString, redirectURL = "/otp_login") {
    const sessionExpiresAt = new Date(expiryString);

    const checkSession = () => {
    const now = new Date();
    if (now >= sessionExpiresAt) {
        clearInterval(sessionCheckInterval);
      window.location.href = "/session_expired";  // or use redirectURL
    }
    };

    // ⏱ Start checking every 10 seconds
    const sessionCheckInterval = setInterval(checkSession, 10000);
}
