import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InfiniteScroll from "./InfiniteScroll";

/**
 * The scroll sentinel.
 *
 * jsdom has no IntersectionObserver and no layout, so a real one would never
 * fire here. The stub below records what was observed and hands the test a
 * trigger, which is the part worth pinning: WHEN the component asks for the
 * next page, and — more importantly — when it does not.
 */

interface Instance {
  callback: IntersectionObserverCallback;
  observed: Element[];
  disconnected: boolean;
}

let instances: Instance[] = [];

class FakeObserver {
  private instance: Instance;

  constructor(callback: IntersectionObserverCallback) {
    this.instance = { callback, observed: [], disconnected: false };
    instances.push(this.instance);
  }

  observe(node: Element) {
    this.instance.observed.push(node);
  }

  disconnect() {
    this.instance.disconnected = true;
  }

  unobserve() {}
  takeRecords() {
    return [];
  }
}

/** Pretend the sentinel scrolled into view. */
const scrollIntoView = (isIntersecting = true) => {
  for (const instance of instances) {
    instance.callback(
      [{ isIntersecting } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
  }
};

beforeEach(() => {
  instances = [];
  vi.stubGlobal("IntersectionObserver", FakeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("InfiniteScroll", () => {
  it("asks for the next page when the sentinel comes into view", () => {
    const onLoadMore = vi.fn();
    render(<InfiniteScroll hasMore loading={false} onLoadMore={onLoadMore} />);

    expect(instances[0].observed).toHaveLength(1);
    scrollIntoView();

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("ignores the sentinel while it is out of view", () => {
    const onLoadMore = vi.fn();
    render(<InfiniteScroll hasMore loading={false} onLoadMore={onLoadMore} />);

    scrollIntoView(false);

    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it("does not stack a second request on top of one already in flight", () => {
    const onLoadMore = vi.fn();
    render(<InfiniteScroll hasMore loading onLoadMore={onLoadMore} />);

    scrollIntoView();

    expect(instances).toHaveLength(0);
    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it("renders nothing at the end of the list", () => {
    const { container } = render(
      <InfiniteScroll hasMore={false} loading={false} onLoadMore={vi.fn()} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("keeps the button as the manual route to the same page", async () => {
    const onLoadMore = vi.fn();
    render(<InfiniteScroll hasMore loading={false} onLoadMore={onLoadMore} label="טען עוד" />);

    await userEvent.click(screen.getByRole("button", { name: "טען עוד" }));

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("stops observing once it is unmounted", () => {
    const { unmount } = render(
      <InfiniteScroll hasMore loading={false} onLoadMore={vi.fn()} />,
    );

    unmount();

    expect(instances[0].disconnected).toBe(true);
  });

  it("works where the browser has no IntersectionObserver at all", async () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    const onLoadMore = vi.fn();

    render(<InfiniteScroll hasMore loading={false} onLoadMore={onLoadMore} label="טען עוד" />);
    await userEvent.click(screen.getByRole("button", { name: "טען עוד" }));

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});
