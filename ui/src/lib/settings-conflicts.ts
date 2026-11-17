/** Find raw sections that overlap pending structured changes. */
export function conflictingSections(
  values: Record<string, unknown>,
  sections: Record<string, string>,
): string[] {
  return Object.keys(sections).filter((section) =>
    Object.keys(values).some((key) =>
      key === section || key.startsWith(`${section}.`) || section.startsWith(`${key}.`),
    ),
  );
}
