from colorama import Fore, Style, init

# Initialize colorama for Windows compatibility
init()

def main():
    print(f"{Fore.CYAN}Hello Universe!{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}🌌 ✨ {Fore.MAGENTA}Hello Universe!{Fore.YELLOW} ✨ 🌌{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'=' * 40}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}Welcome to our simple Python app!{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'=' * 40}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
