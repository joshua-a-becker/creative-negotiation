import React from "react";
import Markdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

// Role narratives are Markdown with a small amount of inline HTML from the
// materials builder (italics, colored/underlined payoff values, indented
// bullet spans, line breaks). Allow exactly that and nothing else: no
// scripts, event handlers, links to elsewhere, or arbitrary tags.
const schema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames || []), "span", "u", "br"],
  attributes: {
    ...defaultSchema.attributes,
    span: ["style"],
    strong: ["style"],
    em: ["style"],
    u: ["style"],
  },
};

export function RoleNarrative({ children }) {
  return (
    <Markdown rehypePlugins={[rehypeRaw, [rehypeSanitize, schema]]}>
      {children}
    </Markdown>
  );
}
