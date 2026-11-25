// Spec 138, regra 4: `if (isLoading || !data)` é o jeito errado de decidir o que
// renderizar, e estava em sete telas de detalhe. Quando a consulta falha, o TanStack
// Query devolve `isLoading: false` com `data: undefined` — a condição continua verdadeira
// e a tela fica em "Carregando…" para sempre, sem erro e sem saída. O conserto é o
// `QueryStateGate` de `components/domain/`; esta regra impede a volta do padrão.

const LOADING_NAME = /^(is)?(Loading|Pending)$|Loading$|Pending$/;
const ERROR_NAME = /error|Error|QueryStateGate/;

function mentionsError(node, sourceCode) {
  return ERROR_NAME.test(sourceCode.getText(node));
}

function isLoadingIdentifier(node) {
  if (node.type === "Identifier") return LOADING_NAME.test(node.name);
  if (node.type === "MemberExpression" && node.property.type === "Identifier") {
    return LOADING_NAME.test(node.property.name);
  }
  return false;
}

function isMissingDataCheck(node) {
  return node.type === "UnaryExpression" && node.operator === "!";
}

export default {
  meta: {
    type: "problem",
    docs: {
      description: "proíbe `if (isLoading || !data)`: com erro de API, isso vira carregando eterno",
    },
    schema: [],
    messages: {
      loadingWithoutError:
        "`isLoading || !data` esconde o erro: com a API falhando, `isLoading` volta a false e `data` fica undefined, e a tela fica em 'Carregando…' para sempre. Use <QueryStateGate> (components/domain) ou trate `isError` explicitamente.",
    },
  },
  create(context) {
    const sourceCode = context.sourceCode ?? context.getSourceCode();
    return {
      IfStatement(node) {
        const test = node.test;
        if (test.type !== "LogicalExpression" || test.operator !== "||") return;
        const parts = [];
        const flatten = (expression) => {
          if (expression.type === "LogicalExpression" && expression.operator === "||") {
            flatten(expression.left);
            flatten(expression.right);
            return;
          }
          parts.push(expression);
        };
        flatten(test);
        const hasLoading = parts.some(isLoadingIdentifier);
        const hasMissingData = parts.some(isMissingDataCheck);
        if (hasLoading && hasMissingData && !mentionsError(test, sourceCode)) {
          context.report({ node: test, messageId: "loadingWithoutError" });
        }
      },
    };
  },
};
