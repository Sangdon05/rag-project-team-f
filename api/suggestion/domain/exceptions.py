from api.shared.exceptions import ApiError


class InvalidSuggestionError(ApiError):
    """제공자 데이터가 불변식을 어김 (빈 문장, id 중복). 서버 데이터 오류이므로 500 INTERNAL_ERROR."""
