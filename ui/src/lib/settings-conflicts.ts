/** Find raw sections that overlap pending structured changes. */
export function conflictingSections(
  values: Record<string, unknown>,
  sections: Record<string, string>,
  profiles: Record<string, unknown> = {},
): string[] {
  return Object.keys(sections).filter((section) =>
    (section === "agent_profiles" && Object.keys(profiles).length > 0) ||
    Object.keys(values).some((key) =>
      key === section || key.startsWith(`${section}.`) || section.startsWith(`${key}.`),
    ),
  );
}
