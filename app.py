"""Source and PyInstaller entry point for the desktop application."""

if __name__ == "__main__":
    from multiprocessing import freeze_support
    from custompresence.desktop import main

    freeze_support()
    main()
