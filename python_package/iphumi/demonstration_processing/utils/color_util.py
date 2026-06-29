from colorama import init, Fore, Style
init()

def color(msg, color=Fore.BLUE):
    return color + msg + Style.RESET_ALL

def blue(msg):
    return color(msg, Fore.BLUE)

def red(msg):
    return color(msg, Fore.RED)

def green(msg):
    return color(msg, Fore.GREEN)

def yellow(msg):
    return color(msg, Fore.YELLOW)
