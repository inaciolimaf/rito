// Regra 7 da spec 006: nenhum componente usa cor literal do Tailwind (ex.: bg-blue-500) —
// só token semântico (bg-surface, text-primary, bg-accent, bg-danger, bg-warning, bg-success...).
// Varre qualquer string/template literal (className, cva(), cn(), clsx()) — não só JSX.

const COLOR_NAMES = [
  "slate",
  "gray",
  "zinc",
  "neutral",
  "stone",
  "red",
  "orange",
  "amber",
  "yellow",
  "lime",
  "green",
  "emerald",
  "teal",
  "cyan",
  "sky",
  "blue",
  "indigo",
  "violet",
  "purple",
  "fuchsia",
  "pink",
  "rose",
  "black",
  "white",
];

const PREFIXES = [
  "bg",
  "text",
  "border",
  "ring",
  "ring-offset",
  "fill",
  "stroke",
  "from",
  "via",
  "to",
  "divide",
  "outline",
  "decoration",
  "caret",
  "shadow",
  "placeholder",
];

const PATTERN = new RegExp(
  `(?:^|\\s)(?:${PREFIXES.join("|")})-(?:${COLOR_NAMES.join("|")})(?:-\\d{2,3})?(?:\\s|$|/)`,
);

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Proíbe classes de cor literal do Tailwind — exige token semântico (spec 006, regra 7).",
    },
    schema: [],
    messages: {
      literalColor:
        "Cor literal do Tailwind ('{{match}}') não é permitida — use um token semântico (bg-surface, text-primary, border-default, bg-accent, bg-danger, bg-warning, bg-success...).",
    },
  },
  create(context) {
    function check(node, raw) {
      const match = PATTERN.exec(raw);
      if (match) {
        context.report({ node, messageId: "literalColor", data: { match: match[0].trim() } });
      }
    }

    return {
      Literal(node) {
        if (typeof node.value === "string") {
          check(node, node.value);
        }
      },
      TemplateElement(node) {
        check(node, node.value.raw);
      },
    };
  },
};

export default rule;
