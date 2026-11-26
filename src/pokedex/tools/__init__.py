"""Read-only Responses tool declarations and the matching server input contracts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SEARCH = 'search_pokedex'
TEAM = 'analyze_team_defense'
MOVE = 'find_move_weaknesses'
CLARIFY = 'clarify_pokedex_question'


class ToolArguments(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class SearchArguments(ToolArguments):
    """Use for ordinary Red/Blue Pokédex questions: profiles, stats, learnsets, encounters, and
    individual facts even when several Pokémon are named. The server searches with the original
    conversation and its configured A/B/C policy. Do not use for a roster's shared defensive
    weaknesses, adding/replacing a team member, or determining which Pokémon are weak to a move.
    """


class TeamArguments(ToolArguments):
    """Use for a specified current team's defensive matchups or adding/replacing a member to cover
    defensive gaps. Include only confirmed current team members, not opponents, examples, or
    proposed candidates. Use 'analyze' for diagnosis, 'add' for a vacant slot, or 'replace' for a
    swap. If a full roster needs a change, clarify whom to replace unless that member is specified.
    Use exact names as given, without guessing, silently correcting, or deduplicating. If the
    current roster or a reference is unclear, ask for clarification instead. Do not use for
    separate factual questions about several Pokémon, learnability, actual damage or win rates.
    """
    intent: Literal['analyze', 'add', 'replace']
    members: list[str] = Field(description='Names of current roster members only, in given order.')
    replace_member: str | None = Field(description='Confirmed current member to swap out, otherwise null.')
    candidate: str | None = Field(description='Explicitly proposed incoming Pokémon, otherwise null.')


class MoveArguments(ToolArguments):
    """Use for a named move's damage classification, its effect when not directly damaging, or
    which Red/Blue Pokémon are weak to that move by basic defensive type matchup. Use the given
    move name, not a Pokémon name, attack type or guessed correction. Clarify an unclear move
    reference. Do not use for who can learn it, actual HP damage, or generic facts unrelated to
    direct damage/weakness.
    """
    move: str


class ClarifyArguments(ToolArguments):
    """Ask one short confirmation if the referenced move, current team roster, outgoing member,
    or proposed incoming candidate is not clear. Use when facts cannot be looked up without guessing the
    referenced entity. Do not use instead of searching an ordinary valid Pokédex question. No
    free-form question text; the server chooses a safe prompt for the reason.
    """
    reason: Literal['team_roster', 'replacement_target', 'candidate_name', 'move_name', 'reference']


_ARGUMENTS = {SEARCH: SearchArguments, TEAM: TeamArguments, MOVE: MoveArguments, CLARIFY: ClarifyArguments}


def function_tools():
    tools = []
    for name, cls in _ARGUMENTS.items():
        schema = cls.model_json_schema()
        tools.append({'type': 'function', 'name': name, 'description': cls.__doc__.strip(), 'strict': True,
                      'parameters': {'type': 'object', 'properties': schema['properties'],
                                     'required': schema.get('required', []), 'additionalProperties': False}})
    return tools


def validate_arguments(name, value):
    if type(name) is not str or name not in _ARGUMENTS or type(value) is not dict:
        raise ValueError('unregistered tool or invalid arguments')
    try:
        return _ARGUMENTS[name].model_validate(value)
    except ValidationError:
        raise ValueError('invalid tool arguments') from None
