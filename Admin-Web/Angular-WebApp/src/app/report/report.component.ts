import { Component, OnInit } from '@angular/core';
import { AngularFirestore } from 'angularfire2/firestore';
import { AngularFireDatabase } from 'angularfire2/database';
import { AngularFireAuth } from 'angularfire2/auth';
import { Observable } from 'rxjs/Observable';
import * as firebase from 'firebase/app';
import { Observer } from 'rxjs/Observer';


@Component({
  selector: 'app-report',
  templateUrl: './report.component.html',
  styleUrls: ['./report.component.css']
})
export class ReportComponent implements OnInit {
  user: Observable<firebase.User>;
  records$: Observable<any>;
  records:Array<any>;
  constructor(public afAuth: AngularFireAuth,private db: AngularFireDatabase) {
    this.afAuth.auth.signInAnonymously();
    this.user = this.afAuth.authState;
  }

  ngOnInit() {
    this.records$ = this.db.list<any>('/records').valueChanges(); 
    this.records$.subscribe(datas=>{ 
          var a : any[] = []; 
          for (var i = 0; i < datas.length; i++) {
            console.log(datas[i]);
            var p = datas[i].split('|');
            var p0 = p[0];
            var p1 = +p[1];
            var p2 = +p[2];
            a.push({ name: p0, order: p1, time:new Date(p2 *1000) });
          }
          this.records = a;          
    });
  }

}
