import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./Markdown.css";

interface Props {
  children: string;
  /** Tighter spacing for markdown inside a chat bubble. */
  compact?: boolean;
}

/** Minimal structural view of an mdast node - enough to walk and patch it. */
interface MdastNode {
  type: string;
  value?: string;
  children?: MdastNode[];
}

const BR_TAG = /^<br\s*\/?>$/i;

// Raw HTML is deliberately NOT parsed. Agent replies are LLM output shaped by
// user input and uploaded documents, so they are untrusted; react-markdown's
// default of escaping every HTML tag is safe by construction, and keeping it
// that way means no sanitiser to get wrong.
//
// The one tag replies actually need is <br>, because it is the only way to
// break a line inside a GFM table cell. Rather than pull in rehype-raw +
// rehype-sanitize for it (measured: +175 kB raw / +54 kB gzipped), this walks
// the tree and turns just that tag into a real mdast hard break. Every other
// tag still renders as literal text.
function remarkBrAsHardBreak() {
  return (tree: MdastNode) => {
    const walk = (node: MdastNode) => {
      if (!node.children) return;
      for (const child of node.children) {
        if (child.type === "html" && BR_TAG.test((child.value ?? "").trim())) {
          child.type = "break";
          delete child.value;
        } else {
          walk(child);
        }
      }
    };
    walk(tree);
  };
}

// The one markdown renderer in the app, so a table in a chat reply and a
// table in the report preview look the same.
//
// remark-gfm is load-bearing: the model answers with GFM tables and
// strikethrough. Without it a table renders as a wall of pipe characters,
// which is exactly how this was reported.
export function Markdown({ children, compact }: Props) {
  return (
    <div className={`ds-markdown${compact ? " ds-markdown--compact" : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBrAsHardBreak]}
        components={{
          // A wide table scrolls inside its own container instead of
          // stretching the conversation column (or the report page).
          table: ({ node: _node, ...props }) => (
            <div className="ds-markdown__table-scroll">
              <table {...props} />
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
