#include <stdio.h>
int main() {
    int s[10], t = 0;
    for(int i = 0; i < 10; i++) {
        scanf("%d", &s[i]);
        t += s[i];
    }
    printf("Sonuc: %f", t / 10.0);
    return 0;
}