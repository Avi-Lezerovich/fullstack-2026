/// <reference types="cypress" />

/**
 * End-to-end (the pyramid top): the whole auth journey in a real browser.
 *
 *   sign up  ->  (auto-logged-in)  ->  log out  ->  log in  ->  view own profile
 *
 * Nothing is mocked — Cypress clicks and types exactly like a user, the frontend
 * POSTs to the real Flask API, and Flask reads/writes real MySQL. This is the only
 * layer that catches wiring bugs the unit/integration tests can't.
 *
 * NOTE: the app uses HashRouter, so routes live under the URL fragment
 * (e.g. `#/signup`, `#/user-posts/7`). We navigate to the first page by hash and
 * then drive the rest through the UI, asserting on `location.hash`.
 *
 * A unique email per run keeps the test Repeatable (F.I.R.S.T.) even against a
 * persistent database with a UNIQUE email constraint.
 */
describe("Auth journey: sign up -> log in -> view profile", () => {
  it("registers a new prosecutor, logs back in, and views their profile", () => {
    // --- Arrange: a unique identity so re-runs never collide on the unique email.
    const stamp = Date.now();
    const name = `Cypress Tester ${stamp}`;
    const email = `cypress+${stamp}@runi.ac.il`;
    const password = "secret123"; // satisfies signup rules: >=8 chars, letter + digit

    // --- Act 1 — SIGN UP -------------------------------------------------------
    cy.visit("/#/signup");
    cy.get('[data-testid="signup-name"]').type(name);
    cy.get('[data-testid="signup-email"]').type(email);
    cy.get('[data-testid="signup-password"]').type(password);
    cy.get('[data-testid="signup-confirm"]').type(password);
    cy.get('[data-testid="signup-submit"]').click();

    // --- Assert 1 — landed home and logged in (the greeting shows our name) -----
    cy.location("hash").should("eq", "#/");
    cy.get('[data-testid="profile-link"]').should("contain.text", name);

    // --- Act 2 — LOG OUT -------------------------------------------------------
    cy.get('[data-testid="logout-button"]').click();
    cy.get('[data-testid="profile-link"]').should("not.exist"); // truly logged out
    cy.get('[data-testid="login-cta"]').should("be.visible");

    // --- Act 3 — LOG IN with the same credentials ------------------------------
    cy.get('[data-testid="login-cta"]').click();
    cy.location("hash").should("eq", "#/login");
    cy.get('[data-testid="login-email"]').type(email);
    cy.get('[data-testid="login-password"]').type(password);
    cy.get('[data-testid="login-submit"]').click();

    cy.location("hash").should("eq", "#/");
    cy.get('[data-testid="profile-link"]').should("contain.text", name);

    // --- Act 4 — VIEW PROFILE (click the greeting) -----------------------------
    cy.get('[data-testid="profile-link"]').click();
    cy.location("hash").should("match", /^#\/user-posts\/\d+$/);

    // --- Assert 4 — the profile page shows THIS user ---------------------------
    cy.contains(name).should("be.visible");
    cy.contains(email).should("be.visible");
    cy.contains("עריכת פרופיל").should("be.visible"); // "Edit profile" only shows on our own profile
  });
});
