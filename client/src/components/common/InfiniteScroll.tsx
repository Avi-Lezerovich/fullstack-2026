import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";

interface Props {
  /** Whether there is another page to fetch. */
  hasMore: boolean;
  /** True while a page is in flight; suppresses a second request. */
  loading: boolean;
  onLoadMore: () => void;
  /** The button's resting label. The busy label is shared. */
  label?: string;
  testId?: string;
}

/**
 * "More posts load as the user scrolls down."
 *
 * An empty div is parked below the last row and watched with an
 * IntersectionObserver; when it comes into view the next page is requested.
 * The observer watches a SENTINEL rather than the scroll position because it
 * costs nothing while the user is elsewhere on the page — no scroll handler
 * firing on every frame, no reading layout to compare offsets — and it works
 * the same whether the list scrolls in the window or inside a dialog.
 *
 * `rootMargin` starts the fetch a screen early, so the page below usually
 * arrives before the reader reaches the bottom.
 *
 * The button stays. It is not a leftover: it is the keyboard and screen-reader
 * path to the next page, the fallback where IntersectionObserver is missing,
 * and the only way to advance the list in an automated browser, where the
 * headless tab reports itself hidden and the observer therefore never fires.
 * Both routes call the same `onLoadMore`.
 */
const InfiniteScroll = ({ hasMore, loading, onLoadMore, label = "טען עוד", testId }: Props) => {
  const sentinel = useRef<HTMLDivElement | null>(null);

  // `onLoadMore` is rebuilt on every render of the parent (it closes over the
  // current item count). Keeping it in a ref lets the observer be created once
  // per hasMore/loading change instead of once per render.
  const loadMore = useRef(onLoadMore);
  loadMore.current = onLoadMore;

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore || loading) return;
    if (typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadMore.current();
      },
      { rootMargin: "600px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loading]);

  if (!hasMore) return null;

  return (
    <Box sx={{ textAlign: "center", mt: 2 }} data-testid={testId}>
      <div ref={sentinel} aria-hidden data-testid="infinite-scroll-sentinel" />
      <Button onClick={onLoadMore} disabled={loading}>
        {loading ? "טוען…" : label}
      </Button>
    </Box>
  );
}; export default InfiniteScroll;
