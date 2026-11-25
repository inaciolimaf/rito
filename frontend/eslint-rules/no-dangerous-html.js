// Spec 138, regra 1: `dangerouslySetInnerHTML` injeta HTML de terceiro no documento da
// aplicação — a mesma origem onde mora o refresh token de 30 dias (`lib/api.ts`). O
// projeto não tem sanitizador, e escrever um à mão é o falso conforto clássico. Onde
// precisar mostrar HTML que não escrevemos, use `<SandboxedHtml>`: um iframe sem
// `allow-scripts` e sem `allow-same-origin`, em que o próprio navegador garante que
// nada executa.

export default {
  meta: {
    type: "problem",
    docs: { description: "proíbe dangerouslySetInnerHTML; use <SandboxedHtml>" },
    schema: [],
    messages: {
      dangerousHtml:
        "dangerouslySetInnerHTML injeta HTML de terceiro na origem da aplicação. Use <SandboxedHtml> (components/domain), que isola o conteúdo num iframe sandbox.",
    },
  },
  create(context) {
    return {
      JSXAttribute(node) {
        if (node.name.type === "JSXIdentifier" && node.name.name === "dangerouslySetInnerHTML") {
          context.report({ node, messageId: "dangerousHtml" });
        }
      },
    };
  },
};
