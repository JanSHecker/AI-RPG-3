export function splitCommandInput(value) {
  if (!value.startsWith("/")) {
    return { command: "", rest: value };
  }
  const match = value.match(/^(\/\S*)([\s\S]*)$/);
  return {
    command: match?.[1] ?? value,
    rest: match?.[2] ?? "",
  };
}

export function completionSuffix(input, suggestion) {
  if (!suggestion) return "";
  if (suggestion.toLowerCase().startsWith(input.toLowerCase())) {
    return suggestion.slice(input.length);
  }
  return "";
}

export function buildSuggestions({ commandInput, isConversation, places, presentNpcs }) {
  const value = commandInput.trimStart();
  const lowerValue = value.toLowerCase();
  if (!value.startsWith("/")) return [];

  if (isConversation) {
    return "/exit".startsWith(lowerValue) ? [{ label: "/exit", value: "/exit" }] : [];
  }

  if (lowerValue.startsWith("/travel ")) {
    const query = lowerValue.slice("/travel ".length).trim();
    return places
      .filter((place) => !query || place.name.toLowerCase().includes(query))
      .slice(0, 6)
      .map((place) => ({ label: `/travel ${place.name}`, value: `/travel ${place.name}` }));
  }
  if (lowerValue.startsWith("/talk ")) {
    const query = lowerValue.slice("/talk ".length).trim();
    return presentNpcs
      .filter((npc) => !query || npc.name.toLowerCase().includes(query))
      .slice(0, 6)
      .map((npc) => ({ label: `/talk ${npc.name}`, value: `/talk ${npc.name}` }));
  }
  return [
    { label: "/travel", value: "/travel " },
    { label: "/talk", value: "/talk " },
  ].filter((item) => item.label.startsWith(lowerValue));
}
