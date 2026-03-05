# Bash/Zsh completion for autograder.py
# Source this file:  source autograder-completion.bash
# Or add to ~/.bashrc / ~/.zshrc:  source /path/to/autograder-completion.bash

# Helper: append trailing space to each COMPREPLY entry (for non-file completions,
# since we register with -o nospace globally to allow seamless dir traversal).
_autograder_add_spaces() {
    local i=0
    for entry in "${COMPREPLY[@]}"; do
        COMPREPLY[$i]="${entry} "
        ((i++))
    done
}

# Helper: complete files/dirs — dirs get /, files get a trailing space
_autograder_complete_path() {
    COMPREPLY=( $(compgen -f -- "$1") )
    local i=0
    for entry in "${COMPREPLY[@]}"; do
        if [[ -d "$entry" ]]; then
            COMPREPLY[$i]="${entry}/"
        else
            COMPREPLY[$i]="${entry} "
        fi
        ((i++))
    done
}

_autograder_complete() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="-t --tests -m --manifest -f --format -o --output -w --workdir -j --jacoco -c --coverage -d --debug -T --timeout --summary --report --check --help"

    case "${prev}" in
        -t|--tests|-m|--manifest|-j|--jacoco|-o|--output|-w|--workdir)
            _autograder_complete_path "${cur}"
            return 0
            ;;
        -f|--format)
            COMPREPLY=( $(compgen -W "json md" -- "${cur}") )
            _autograder_add_spaces
            return 0
            ;;
        -T|--timeout)
            return 0
            ;;
    esac

    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        _autograder_add_spaces
        return 0
    fi

    # Default: file completion (positional JAR argument)
    _autograder_complete_path "${cur}"
    return 0
}

# -o nospace prevents the shell from appending a space after completions,
# letting us control it: dirs get /, everything else gets a manual space.
complete -o nospace -F _autograder_complete autograder
complete -o nospace -F _autograder_complete autograder.py
complete -o nospace -F _autograder_complete ./autograder.py
