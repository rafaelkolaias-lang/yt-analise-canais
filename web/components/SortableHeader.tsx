"use client";

/**
 * Header de coluna clicável que cicla entre 3 estados na hora do clique:
 *   1. desc  (maior → menor)
 *   2. asc   (menor → maior)
 *   3. default (volta pro sort default da aba)
 *
 * Como sort é uma string única no estado dos filtros (ex: "subs_desc",
 * "subs_asc", "vpd_desc"), este componente apenas mapeia (coluna, direção)
 * pro sort_key e dispara um callback.
 */

type Props<T extends string> = {
  /** Texto visível do header (ex: "Inscritos"). */
  label: string;
  /** Identificador da coluna (ex: "subs", "vpd"). */
  columnKey: string;
  /** Sort key atualmente ativo (ex: "subs_desc"). */
  currentSort: T;
  /** Sort key default (volta pra ele no 3º clique, ou no 2º se não houver `ascKey`). */
  defaultSort: T;
  /** Sort key da coluna em desc (ex: "subs_desc"). */
  descKey: T;
  /**
   * Sort key da coluna em asc (ex: "subs_asc"). Se não passado, a coluna
   * só ordena em desc (toggle 2 estados: desc ↔ default).
   */
  ascKey?: T;
  /** Disparado com o próximo sort key (já calculado). */
  onChange: (next: T) => void;
  /** Estilo extra (ex: text-align: right). */
  style?: React.CSSProperties;
};

export function SortableHeader<T extends string>({
  label,
  currentSort,
  defaultSort,
  descKey,
  ascKey,
  onChange,
  style,
}: Props<T>) {
  // Direção atual nesta coluna (se for; senão, null)
  const dir: "desc" | "asc" | null =
    currentSort === descKey
      ? "desc"
      : ascKey && currentSort === ascKey
      ? "asc"
      : null;

  const arrow = dir === "desc" ? "↓" : dir === "asc" ? "↑" : "";

  function handleClick() {
    if (dir === null) {
      onChange(descKey);
    } else if (dir === "desc") {
      // se a coluna tem asc, vai pra asc; senão volta ao default
      onChange(ascKey ?? defaultSort);
    } else {
      // asc → volta ao default
      onChange(defaultSort);
    }
  }

  return (
    <th
      onClick={handleClick}
      style={{
        cursor: "pointer",
        userSelect: "none",
        ...style,
      }}
      aria-sort={
        dir === "desc" ? "descending" : dir === "asc" ? "ascending" : "none"
      }
      title="Clique para ordenar"
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        {label}
        <span
          style={{
            opacity: dir ? 1 : 0.25,
            color: dir ? "var(--accent)" : "inherit",
            fontSize: 11,
            minWidth: 8,
          }}
        >
          {arrow || "↕"}
        </span>
      </span>
    </th>
  );
}
