from checker import Checker

if __name__ == '__main__':
    checker = Checker('live_74275b9b2b8b44d8ad156db03d2008ed')
    tasks = checker.client.tasks()

    checks = checker.run_checks(tasks)
    output = 'Found {} potential issues of types: {}\n\n\n'.format(
        checks['count'],
        checks['types']
    )
    for check in checks['flagged']:
        output += 'Issue type: {}\nSeverity: {}\nAnnotations: {}\nTask: {}\nExplanation: {}\n\n'.format(
            check['type'],
            check['severity'],
            check['annotations'],
            check['task'],
            check['explanation']
        )

    print(output)
