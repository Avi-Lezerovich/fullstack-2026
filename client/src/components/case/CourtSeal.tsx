/**
 * The court's seal, stamped on a case that has been decided.
 *
 * It appears for exactly two statuses - `verdict_reached` and `closed` - and
 * that restraint is the whole effect. A mark on every case is decoration; a
 * mark that appears only once a judge has ruled is something a reader learns to
 * scan the feed for, and it gives "still arguing" and "decided" a visible
 * difference that costs no words.
 *
 * Deliberately not a status indicator. `CaseStatusChip` is that, it sits beside
 * this, and it says which of the two states the case is in. The seal says the
 * coarser thing - the court is finished here - the way a paper court would:
 * pressed crooked, in thin ink, **over** whatever was already on the page.
 *
 * --- why it is positioned rather than laid out -----------------------------
 *
 * The first version was a flex sibling of the title, which is the tidy answer
 * and the wrong one: it reserved a column, pushed the heading aside, and looked
 * like an icon that had been given a seat. A stamp does not get a seat. It
 * lands where it lands and the text goes under it.
 *
 * So it is absolutely positioned, and two consequences follow that no caller
 * should have to think about:
 *
 *   `pointerEvents: none`  - it lies across a heading, an author link and a
 *     defendant name. Without this it would silently eat clicks on all three,
 *     and the failure would look like a broken link rather than like a seal.
 *   `mixBlendMode: multiply` and a low opacity - ink, not sticker. The text has
 *     to stay readable *through* it, because the text is the point and the seal
 *     is only the endorsement.
 *
 * No tooltip, for the same reason: a tooltip needs pointer events. The chip
 * beside it already carries the status in text, which is also why this is
 * `aria-hidden` - announcing it would read the same fact out twice.
 *
 * The parent needs `position: relative`; both call sites set it.
 */

import Box from "@mui/material/Box";

import type { CaseStatus } from "../../types";

/** The only two states a decided case can be in. */
const SEALED: readonly CaseStatus[] = ["verdict_reached", "closed"];

export const isSealed = (status: CaseStatus): boolean => SEALED.includes(status);

interface Props {
  status: CaseStatus;
  /** `card` rides on the feed card; `page` is the big one on the case page. */
  variant?: "card" | "page";
}

const CourtSeal = ({ status, variant = "card" }: Props) => {
  if (!isSealed(status)) return null;

  const page = variant === "page";

  return (
    <Box
      component="img"
      src={`${import.meta.env.BASE_URL}lolsuit-seal.svg`}
      alt=""
      aria-hidden
      data-testid="court-seal"
      data-variant={variant}
      sx={{
        position: "absolute",
        // A LOGICAL property, not `left` or `right`, and that is the point:
        // this app renders RTL, and the physical ones are not reliable here -
        // measured, `right: -6` landed on the visual right inside a card and on
        // the visual left elsewhere, because whether stylis-plugin-rtl mirrors
        // a given declaration is not a thing to guess at per call site.
        // `inset-inline-end` is the end of the reading direction by definition:
        // the visual left on a Hebrew page, which is the side with the space,
        // and still correct if any of this is ever rendered LTR.
        insetInlineEnd: page ? { xs: -8, sm: 8 } : -6,
        top: page ? { xs: -12, sm: -18 } : -10,
        // Big enough to read as a seal. The mark carries text on two arcs, and
        // much below this it turns into grey noise - at which point it reads as
        // a stray icon and the "this case is finished" signal is gone.
        width: page ? { xs: 132, sm: 190 } : { xs: 72, sm: 96 },
        height: "auto",
        // A stamp is never quite straight; a perfectly upright one reads as a
        // logo. Enough to be felt, not enough to look like a rendering bug.
        transform: "rotate(-8deg)",
        opacity: page ? 0.42 : 0.38,
        mixBlendMode: "multiply",
        // It lies across a heading and two links. Never eat their clicks.
        pointerEvents: "none",
        // Above the text it is stamped on, below anything a user can operate.
        zIndex: 1,
      }}
    />
  );
};

export default CourtSeal;
