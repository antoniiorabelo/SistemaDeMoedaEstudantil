import re

from django.core.exceptions import ValidationError


def normalizar_cpf(value):
    return re.sub(r'[.\-\s]', '', value)


def validar_cpf(value):
    cpf = normalizar_cpf(value)
    if not re.fullmatch(r'\d{11}', cpf) or len(set(cpf)) == 1:
        raise ValidationError('Informe um CPF válido com 11 dígitos.')
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[tamanho]):
            raise ValidationError('Os dígitos verificadores do CPF são inválidos.')


def normalizar_rg(value):
    return re.sub(r'[.\-\s]', '', value).upper()


def validar_rg(value):
    if not re.fullmatch(r'[0-9A-Z]{3,20}', normalizar_rg(value)):
        raise ValidationError('Informe um RG com 3 a 20 letras ou números.')
