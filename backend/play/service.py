from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable

from play.commands import ParsedPlayInput, parse_play_input
from play_repository import (
    append_play_message,
    get_npc_for_play,
    get_play_state,
    list_places_for_play,
    list_present_npcs_for_play,
    set_conversation_mode,
    set_default_mode,
    travel_play_session,
)


NpcReplyFactory = Callable[[str, str], Awaitable[str]]


class PlayInputError(ValueError):
    pass


@dataclass(frozen=True)
class PlayContext:
    world_id: str
    reply_to_npc: NpcReplyFactory


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _resolve_place(world_id: str, value: str) -> dict:
    query = value.strip()
    if not query:
        raise PlayInputError("Travel command requires a place.")

    normalized = _normalize(query)
    for place in list_places_for_play(world_id):
        if place.get("id") == query or _normalize(place.get("name", "")) == normalized:
            return place
    raise PlayInputError(f"Unknown place: {query}")


def _resolve_present_npc(world_id: str, value: str) -> dict:
    query = value.strip()
    if not query:
        raise PlayInputError("Talk command requires a character.")

    normalized = _normalize(query)
    for npc in list_present_npcs_for_play(world_id):
        if npc.get("id") == query or _normalize(npc.get("name", "")) == normalized:
            return npc
    raise PlayInputError(f"That character is not present here: {query}")


class PlayState(ABC):
    def __init__(self, context: PlayContext, session: dict) -> None:
        self.context = context
        self.session = session

    @abstractmethod
    async def handle(self, parsed: ParsedPlayInput) -> dict:
        raise NotImplementedError


class DefaultPlayState(PlayState):
    async def handle(self, parsed: ParsedPlayInput) -> dict:
        if not parsed.is_command:
            state = get_play_state(self.context.world_id)
            if not state:
                raise PlayInputError("World not found.")
            return state

        if parsed.command == "travel":
            place = _resolve_place(self.context.world_id, parsed.argument)
            return travel_play_session(self.context.world_id, place["id"])

        if parsed.command == "talk":
            npc = _resolve_present_npc(self.context.world_id, parsed.argument)
            set_conversation_mode(self.context.world_id, npc["id"])
            append_play_message(
                self.context.world_id,
                "system",
                f"You start a conversation with {npc['name']}.",
                npc["id"],
            )
            state = get_play_state(self.context.world_id)
            if not state:
                raise PlayInputError("World not found.")
            return state

        if parsed.command == "exit":
            raise PlayInputError("You are not in a conversation.")

        raise PlayInputError(f"Unknown command: /{parsed.command}")


class ConversationPlayState(PlayState):
    async def handle(self, parsed: ParsedPlayInput) -> dict:
        npc_id = self.session.get("conversation_npc_id")
        if not npc_id:
            set_default_mode(self.context.world_id)
            raise PlayInputError("No active conversation partner.")

        npc = get_npc_for_play(self.context.world_id, npc_id)
        if not npc:
            set_default_mode(self.context.world_id)
            raise PlayInputError("Conversation partner is no longer available.")

        if parsed.is_command:
            if parsed.command == "exit":
                append_play_message(
                    self.context.world_id,
                    "system",
                    f"You end the conversation with {npc['name']}.",
                    npc_id,
                )
                return set_default_mode(self.context.world_id)

            if parsed.command in {"travel", "talk"}:
                raise PlayInputError("Exit the current conversation before using that command.")

            raise PlayInputError(f"Unknown command: /{parsed.command}")

        if not parsed.raw:
            raise PlayInputError("Message cannot be empty.")

        append_play_message(self.context.world_id, "player", parsed.raw, npc_id)
        reply = await self.context.reply_to_npc(npc_id, parsed.raw)
        append_play_message(self.context.world_id, "npc", reply, npc_id)
        state = get_play_state(self.context.world_id)
        if not state:
            raise PlayInputError("World not found.")
        return state


def _state_for(context: PlayContext) -> PlayState:
    state = get_play_state(context.world_id)
    if not state:
        raise PlayInputError("World not found.")

    session = state["session"]
    if session.get("mode") == "conversation":
        return ConversationPlayState(context, session)
    return DefaultPlayState(context, session)


async def submit_play_input(world_id: str, value: str, reply_to_npc: NpcReplyFactory) -> dict:
    parsed = parse_play_input(value)
    if not parsed.raw:
        raise PlayInputError("Input cannot be empty.")

    context = PlayContext(world_id=world_id, reply_to_npc=reply_to_npc)
    return await _state_for(context).handle(parsed)
