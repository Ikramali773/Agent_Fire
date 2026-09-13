import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Markdown } from "./Markdown";

afterEach(cleanup);

describe("Markdown", () => {
  it("renders a GFM table instead of a wall of pipe characters", () => {
    // This is the reported bug: replies routinely contain tables, and
    // without remark-gfm they showed on screen as literal `|` and `---`.
    const { container } = render(
      <Markdown>{"| Item | Value |\n| --- | --- |\n| Occupancy | Residential |\n"}</Markdown>,
    );

    expect(container.querySelector("table")).not.toBeNull();
    expect(screen.getByRole("columnheader", { name: "Item" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "Residential" })).toBeTruthy();
  });

  it("puts a wide table in its own scroll container", () => {
    const { container } = render(<Markdown>{"| A | B |\n| --- | --- |\n| 1 | 2 |\n"}</Markdown>);

    expect(container.querySelector(".ds-markdown__table-scroll > table")).not.toBeNull();
  });

  it("renders <br> inside a table cell as a real line break", () => {
    // The only way to break a line in a GFM cell, and the single reason
    // the local remark plugin exists.
    const { container } = render(
      <Markdown>{"| Item | Why |\n| --- | --- |\n| Height | Roof level<br>above access |\n"}</Markdown>,
    );

    expect(container.querySelector("td br")).not.toBeNull();
  });

  it("accepts every spelling of the tag", () => {
    const { container } = render(<Markdown>{"one<br>two<br/>three<br />four"}</Markdown>);

    expect(container.querySelectorAll("br")).toHaveLength(3);
  });

  it("renders headings, emphasis, lists and links", () => {
    const { container } = render(
      <Markdown>{"### Next steps\n\n1. Confirm **load**\n2. Upload the *drawings*\n\n[code](https://example.com)\n"}</Markdown>,
    );

    expect(screen.getByRole("heading", { level: 3, name: "Next steps" })).toBeTruthy();
    expect(container.querySelector("ol li strong")).not.toBeNull();
    expect(container.querySelector("em")).not.toBeNull();
    expect(screen.getByRole("link", { name: "code" }).getAttribute("href")).toBe("https://example.com");
  });

  it("escapes raw HTML instead of rendering it", () => {
    // Load-bearing security property, not a nicety: this content is LLM
    // output shaped by user input and uploaded documents, so it is
    // untrusted. react-markdown escaping every tag by default is what
    // makes the renderer safe with no sanitiser to get wrong - anything
    // that starts parsing raw HTML has to break this test first.
    const { container } = render(
      <Markdown>{'<img src=x onerror="alert(1)"> <b>bold?</b> <a href="javascript:alert(1)">link?</a>'}</Markdown>,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("<b>bold?</b>");
  });

  it("does not let a <script> tag through", () => {
    const { container } = render(<Markdown>{'<script>alert("xss")</script>'}</Markdown>);

    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("alert");
  });

  it("adds the compact modifier only when asked", () => {
    const plain = render(<Markdown>text</Markdown>).container;
    expect(plain.querySelector(".ds-markdown--compact")).toBeNull();
    cleanup();

    const compact = render(<Markdown compact>text</Markdown>).container;
    expect(compact.querySelector(".ds-markdown--compact")).not.toBeNull();
  });

  it("renders an empty string without crashing", () => {
    const { container } = render(<Markdown>{""}</Markdown>);

    expect(container.querySelector(".ds-markdown")).not.toBeNull();
  });
});
