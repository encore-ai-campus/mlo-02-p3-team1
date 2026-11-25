"""화면에 실행 ID(ST01 ...) 대신 분류 태그(DS-01 ...)를 보여 주는 템플릿 필터. 사용: {% load game_tags %} {{ code|game_tag }}"""
from django import template

from telemetry.catalog import tag_for

register = template.Library()


@register.filter
def game_tag(code):
    return tag_for(code) if code else code
