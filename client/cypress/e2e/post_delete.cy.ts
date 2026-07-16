/// <reference types="cypress" />

/**
 * End-to-end (the pyramid top): the whole delete-post journey in a real browser.
 *
 *   sign up  ->  (auto-logged-in)  ->  create a post  ->  delete it  ->  gone from the feed
 *
 * Nothing is mocked — Cypress clicks and types exactly like a user, the frontend
 * talks to the real Flask API, and Flask reads/writes real MySQL.
 *
 * NOTE: the app uses HashRouter, so routes live under the URL fragment
 * (e.g. `#/new-post`). We navigate by hash and assert on `location.hash`.
 *
 * A unique title per run keeps the test Repeatable (F.I.R.S.T.) even against a
 * persistent database — it also lets us find THIS post among any others already
 * in the feed.
 */
describe("Delete post journey: sign up -> create post -> delete post", () => {
  it("creates a lawsuit and then deletes it, removing it from the feed", () => {
    // --- Arrange: a unique identity + unique post title so re-runs never collide.
    const stamp = Date.now();
    const name = `Cypress Tester ${stamp}`;
    const email = `cypress+${stamp}@runi.ac.il`;
    const password = "secret123"; // satisfies signup rules: >=8 chars, letter + digit
    const title = `תביעת בדיקה ${stamp}`;

    // --- Act 1 — SIGN UP -------------------------------------------------------
    cy.visit("/#/signup");
    cy.get('[data-testid="signup-name"]').type(name);
    cy.get('[data-testid="signup-email"]').type(email);
    cy.get('[data-testid="signup-password"]').type(password);
    cy.get('[data-testid="signup-confirm"]').type(password);
    cy.get('[data-testid="signup-submit"]').click();
    cy.location("hash").should("eq", "#/");

    // --- Act 2 — CREATE A POST --------------------------------------------------
    cy.visit("/#/new-post");
    cy.get('[data-testid="new-post-title"]').type(title);
    cy.get('[data-testid="new-post-defendant"]').type("הנתבע לדוגמה");
    cy.get('[data-testid="new-post-body"] .ProseMirror').type("פירוט התביעה לצורך הבדיקה.");
    cy.get('[data-testid="new-post-submit"]').click();

    // --- Assert 2 — back on the feed, the new post is visible ------------------
    cy.location("hash").should("eq", "#/");
    cy.contains(title).should("be.visible");

    // --- Act 3 — DELETE THE POST -------------------------------------------------
    cy.contains(title)
      .closest('[data-testid="post-card"]')
      .find('[data-testid="post-delete-button"]')
      .click();
    cy.get('[data-testid="post-delete-confirm"]').click();

    // --- Assert 3 — the post is gone from the feed ------------------------------
    cy.contains(title).should("not.exist");
  });
});
