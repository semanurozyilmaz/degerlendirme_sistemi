#include <stdio.h>

int main() {
    int a, b;
    long c = 1;

    scanf("%d", &a);

    if (a >= 0) {
        for (b = 1; b <= a; b++) {
            c = c * b;
        }
        printf("%ld\n", c);
    }
    
    return 0;
}